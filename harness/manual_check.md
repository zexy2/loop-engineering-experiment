# Run B — Fixed Manual Check Script (human verification loop)

The human runs these checks **in order** after each agent turn, using `curl`.
On the **first failure**, stop checking, paste the raw command + output to the
agent as `This failed: <output>. Fix it.` and end the turn.
This list is fixed for the whole experiment — no improvisation.

Setup per turn:

```bash
cd runs/run-B-turnbased
python3 -m venv .venv 2>/dev/null; .venv/bin/pip install -r requirements.txt -q
rm -f taskflow.db
.venv/bin/python -m uvicorn app.main:app --port 8000 &   # then:
KEYS=$(.venv/bin/python -m app.seed)
ADMIN=$(echo "$KEYS" | sed -n 's/^admin_key=//p'); MEMBER=$(echo "$KEYS" | sed -n 's/^member_key=//p')
```

Checks (expected result in parentheses):

1. `curl -si localhost:8000/v1/health` (200, `{"status":"ok"}`)
2. `curl -si localhost:8000/v1/projects` (401, error envelope with code `unauthorized`)
3. `curl -si -H "X-API-Key: $MEMBER" -X POST localhost:8000/v1/projects -H 'Content-Type: application/json' -d '{"name":"  Demo  "}'` (201, name trimmed to `"Demo"`, `task_counts` all zero)
4. Reuse the project id `P` from step 3:
   `curl -si -H "X-API-Key: $MEMBER" -X POST localhost:8000/v1/projects/P/tasks -d '{"title":"Task one","tags":["URGENT","Home"]}' -H 'Content-Type: application/json'` (201, tags `["urgent","home"]`, status `todo`, priority 3)
5. `curl -si -H "X-API-Key: $MEMBER" -X POST localhost:8000/v1/projects/P/tasks -d '{"title":"t","tags":["A","a"]}' -H 'Content-Type: application/json'` (409, code `conflict`)
6. `curl -si -H "X-API-Key: $MEMBER" -X PATCH localhost:8000/v1/tasks/T -d '{}' -H 'Content-Type: application/json'` with task id `T` from step 4 (422, `validation_error`)
7. `curl -si -H "X-API-Key: $MEMBER" -X POST localhost:8000/v1/tasks/T/complete` (200, status `done`), repeat the same command (422, message mentions already done)
8. `curl -si -H "X-API-Key: $MEMBER" -X PATCH localhost:8000/v1/tasks/T -d '{"status":"todo"}' -H 'Content-Type: application/json'` (422 — done→todo forbidden)
9. `curl -si -H "X-API-Key: $MEMBER" "localhost:8000/v1/projects?limit=0"` (422)
10. `curl -si -H "X-API-Key: $ADMIN" localhost:8000/v1/projects/P` (404 — cross-key scoping)
11. `curl -si -H "X-API-Key: $MEMBER" localhost:8000/v1/admin/keys` (403), then with `$ADMIN` (200, no raw keys in body)
12. Bulk: 2 valid + 1 whitespace-title item → (207; statuses 201/422/201)
13. `curl -si -H "X-API-Key: $MEMBER" localhost:8000/v1/stats` (200; has projects/tasks/by_status/overdue)
14. Restart server with `RATE_LIMIT_PER_MINUTE=5`, re-seed, then 7 fast
    `GET /v1/projects` with the member key (429 by request 6, envelope
    `rate_limited`, headers `X-RateLimit-Limit: 5`, `X-RateLimit-Remaining: 0`,
    `Retry-After` present; `GET /v1/health` still 200)

Stop condition: all 14 checks pass in one sweep, or 8 feedback turns used.
