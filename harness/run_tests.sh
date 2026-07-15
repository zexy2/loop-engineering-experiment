#!/usr/bin/env bash
# Usage: harness/run_tests.sh runs/run-A-oneshot
#
# Black-box scoring of one run:
#   Phase 1: functional suite  (rate limit raised so it can't interfere)
#   Phase 2: rate-limit suite  (fresh server, RATE_LIMIT_PER_MINUTE=15, fresh keys)
#
# Writes results/<run-name>-score.json and prints a summary.
# The agent never sees this script or the tests.

set -uo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$HARNESS_DIR")"
RUN_DIR="$(cd "$1" 2>/dev/null && pwd)" || { echo "run dir '$1' not found"; exit 2; }
RUN_NAME="$(basename "$RUN_DIR")"
RESULTS_DIR="$ROOT_DIR/results"
VENV="$HARNESS_DIR/.venv"
PORT="${PORT:-8000}"
BASE="http://127.0.0.1:$PORT"

mkdir -p "$RESULTS_DIR"

# ---------- harness venv (pytest + httpx only; never touches the run's env) ----
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" -q install pytest httpx >/dev/null
fi

# ---------- run's own venv (its requirements.txt) ------------------------------
APP_VENV="$RUN_DIR/.harness-venv"
if [ ! -d "$APP_VENV" ]; then
  python3 -m venv "$APP_VENV"
fi
if [ -f "$RUN_DIR/requirements.txt" ]; then
  "$APP_VENV/bin/pip" -q install -r "$RUN_DIR/requirements.txt" >/dev/null 2>&1
fi
# uvicorn is required by the spec's start command; install it in case the
# run's requirements.txt forgot to list it (that omission is logged, not fatal)
"$APP_VENV/bin/pip" -q install uvicorn >/dev/null 2>&1

SERVER_PID=""
cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" >/dev/null 2>&1
  wait "$SERVER_PID" 2>/dev/null
  SERVER_PID=""
}
trap cleanup EXIT

start_server() { # $1 = RATE_LIMIT_PER_MINUTE value
  cleanup
  # safety: kill anything still holding the port (e.g. a server the agent left running)
  lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null
  sleep 0.3
  rm -f "$RUN_DIR/taskflow.db"
  ( cd "$RUN_DIR" && exec env RATE_LIMIT_PER_MINUTE="$1" "$APP_VENV/bin/python" -m uvicorn app.main:app --port "$PORT" \
      >"$RESULTS_DIR/$RUN_NAME-server.log" 2>&1 ) &
  SERVER_PID=$!
  for _ in $(seq 1 30); do
    if curl -s -o /dev/null "$BASE/v1/health"; then return 0; fi
    sleep 0.5
  done
  echo "SERVER FAILED TO START — see $RESULTS_DIR/$RUN_NAME-server.log"
  return 1
}

seed_keys() {
  local out
  out=$( cd "$RUN_DIR" && "$APP_VENV/bin/python" -m app.seed 2>>"$RESULTS_DIR/$RUN_NAME-server.log" )
  ADMIN_KEY=$(echo "$out" | sed -n 's/^admin_key=//p' | head -1)
  MEMBER_KEY=$(echo "$out" | sed -n 's/^member_key=//p' | head -1)
  if [ -z "$ADMIN_KEY" ] || [ -z "$MEMBER_KEY" ]; then
    echo "SEED FAILED — output was:"; echo "$out"
    return 1
  fi
}

PHASE1_PASS=0; PHASE1_FAIL=0; PHASE2_PASS=0; PHASE2_FAIL=0
SERVER_OK=true

# ================= PHASE 1: functional =================
echo "=== Phase 1: functional suite ($RUN_NAME) ==="
if start_server 1000000 && seed_keys; then
  OUT=$(env API_BASE="$BASE" ADMIN_KEY="$ADMIN_KEY" MEMBER_KEY="$MEMBER_KEY" \
    "$VENV/bin/python" -m pytest "$HARNESS_DIR/acceptance_tests" \
    --ignore="$HARNESS_DIR/acceptance_tests/test_z_ratelimit.py" \
    -q --tb=line 2>&1 | tee "$RESULTS_DIR/$RUN_NAME-phase1.txt" | tail -5)
  PHASE1_PASS=$(grep -oE '[0-9]+ passed' <<<"$OUT" | grep -oE '[0-9]+' || echo 0)
  PHASE1_FAIL=$(( $(grep -oE '[0-9]+ failed' <<<"$OUT" | grep -oE '[0-9]+' || echo 0) \
              + $(grep -oE '[0-9]+ error'  <<<"$OUT" | grep -oE '[0-9]+' || echo 0) ))
else
  SERVER_OK=false
fi

# ================= PHASE 2: rate limiting =================
echo "=== Phase 2: rate-limit suite ($RUN_NAME) ==="
if $SERVER_OK && start_server 15 && seed_keys; then
  OUT=$(env API_BASE="$BASE" ADMIN_KEY="$ADMIN_KEY" MEMBER_KEY="$MEMBER_KEY" \
    RL_PHASE=1 RATE_LIMIT_PER_MINUTE=15 \
    "$VENV/bin/python" -m pytest "$HARNESS_DIR/acceptance_tests/test_z_ratelimit.py" \
    -q --tb=line 2>&1 | tee "$RESULTS_DIR/$RUN_NAME-phase2.txt" | tail -5)
  PHASE2_PASS=$(grep -oE '[0-9]+ passed' <<<"$OUT" | grep -oE '[0-9]+' || echo 0)
  PHASE2_FAIL=$(( $(grep -oE '[0-9]+ failed' <<<"$OUT" | grep -oE '[0-9]+' || echo 0) \
              + $(grep -oE '[0-9]+ error'  <<<"$OUT" | grep -oE '[0-9]+' || echo 0) ))
fi

cleanup

TOTAL_PASS=$((PHASE1_PASS + PHASE2_PASS))
TOTAL_FAIL=$((PHASE1_FAIL + PHASE2_FAIL))
TOTAL=$((TOTAL_PASS + TOTAL_FAIL))
if [ "$TOTAL" -gt 0 ]; then
  RATE=$(python3 -c "print(round(100*$TOTAL_PASS/$TOTAL,1))")
else
  RATE=0
fi

cat > "$RESULTS_DIR/$RUN_NAME-score.json" <<EOF
{
  "run": "$RUN_NAME",
  "timestamp": "$(date -u +%FT%TZ)",
  "server_started": $SERVER_OK,
  "phase1": {"passed": $PHASE1_PASS, "failed": $PHASE1_FAIL},
  "phase2_ratelimit": {"passed": $PHASE2_PASS, "failed": $PHASE2_FAIL},
  "total": {"passed": $TOTAL_PASS, "failed": $TOTAL_FAIL, "pass_rate_pct": $RATE}
}
EOF

echo ""
echo "==================== SCORE: $RUN_NAME ===================="
cat "$RESULTS_DIR/$RUN_NAME-score.json"
