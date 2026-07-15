"""Reference implementation of SPEC.md — used ONLY to validate the hidden
acceptance suite (calibration). Never shown to experiment agents."""
import hashlib
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

import os

DB_PATH = os.environ.get("DB_PATH", "taskflow.db")
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))

app = FastAPI()

# ---------------------------------------------------------------- db helpers

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS keys(
            id TEXT PRIMARY KEY, key_hash TEXT UNIQUE, role TEXT,
            created_at TEXT, request_count INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS projects(
            id TEXT PRIMARY KEY, key_id TEXT, name TEXT, description TEXT,
            created_at TEXT);
        CREATE TABLE IF NOT EXISTS tasks(
            id TEXT PRIMARY KEY, key_id TEXT, project_id TEXT, title TEXT,
            status TEXT, priority INTEGER, due_date TEXT, tags TEXT,
            created_at TEXT, updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE);
        """
    )
    conn.commit()
    conn.close()


init_db()

# ---------------------------------------------------------------- utilities

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def err(status, code, message):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def parse_ts(s):
    if not isinstance(s, str) or not ISO_RE.match(s):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# rate limiting: fixed window per key
_window = {}  # key_id -> (window_start_epoch_min, count)


def check_rate(key_id):
    minute = int(time.time() // 60)
    start, count = _window.get(key_id, (minute, 0))
    if start != minute:
        start, count = minute, 0
    count += 1
    _window[key_id] = (start, count)
    remaining = max(0, RATE_LIMIT - count)
    exceeded = count > RATE_LIMIT
    retry = 60 - int(time.time() % 60)
    return exceeded, remaining, retry


# ---------------------------------------------------------------- middleware

@app.middleware("http")
async def auth_and_rate(request: Request, call_next):
    path = request.url.path
    if path == "/v1/health":
        return await call_next(request)
    if not path.startswith("/v1"):
        return err(404, "not_found", "no such route")

    key = request.headers.get("X-API-Key")
    if not key:
        return err(401, "unauthorized", "missing API key")
    kh = hashlib.sha256(key.encode()).hexdigest()
    conn = db()
    row = conn.execute("SELECT * FROM keys WHERE key_hash=?", (kh,)).fetchone()
    if not row:
        conn.close()
        return err(401, "unauthorized", "unknown API key")
    conn.execute("UPDATE keys SET request_count=request_count+1 WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()

    exceeded, remaining, retry = check_rate(row["id"])
    if exceeded:
        resp = err(429, "rate_limited", "rate limit exceeded")
    else:
        request.state.key_id = row["id"]
        request.state.role = row["role"]
        resp = await call_next(request)
    resp.headers["X-RateLimit-Limit"] = str(RATE_LIMIT)
    resp.headers["X-RateLimit-Remaining"] = str(remaining)
    if exceeded:
        resp.headers["Retry-After"] = str(retry)
    return resp


# ---------------------------------------------------------------- serializers

def project_out(conn, row):
    counts = {"todo": 0, "in_progress": 0, "done": 0}
    for r in conn.execute("SELECT status, COUNT(*) c FROM tasks WHERE project_id=? GROUP BY status", (row["id"],)):
        counts[r["status"]] = r["c"]
    return {
        "id": row["id"], "name": row["name"], "description": row["description"],
        "created_at": row["created_at"], "task_counts": counts,
    }


def task_out(row):
    return {
        "id": row["id"], "project_id": row["project_id"], "title": row["title"],
        "status": row["status"], "priority": row["priority"],
        "due_date": row["due_date"], "tags": json.loads(row["tags"]),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


# ---------------------------------------------------------------- validation

async def read_json(request):
    try:
        body = await request.body()
        if not body:
            return None, err(422, "validation_error", "empty body")
        return json.loads(body), None
    except json.JSONDecodeError:
        return None, err(422, "validation_error", "malformed JSON")


def validate_project_fields(data, partial=False):
    allowed = {"name", "description"}
    unknown = set(data) - allowed
    if unknown:
        return None, f"unknown fields: {sorted(unknown)}"
    out = {}
    if "name" in data:
        if not isinstance(data["name"], str):
            return None, "name must be a string"
        name = data["name"].strip()
        if not (1 <= len(name) <= 100):
            return None, "name must be 1-100 chars after trimming"
        out["name"] = name
    elif not partial:
        return None, "name is required"
    if "description" in data:
        d = data["description"]
        if d is not None and (not isinstance(d, str) or len(d) > 500):
            return None, "description must be <=500 chars"
        out["description"] = d
    return out, None


def validate_task_fields(data, partial=False, allow_project=False):
    allowed = {"title", "status", "priority", "due_date", "tags"}
    if allow_project:
        allowed.add("project_id")
    unknown = set(data) - allowed
    if unknown:
        return None, f"unknown fields: {sorted(unknown)}", None
    out = {}
    if "title" in data:
        if not isinstance(data["title"], str):
            return None, "title must be a string", None
        t = data["title"].strip()
        if not (1 <= len(t) <= 200):
            return None, "title must be 1-200 chars after trimming", None
        out["title"] = t
    elif not partial:
        return None, "title is required", None
    if "status" in data:
        if data["status"] not in ("todo", "in_progress", "done"):
            return None, "invalid status", None
        out["status"] = data["status"]
    if "priority" in data:
        p = data["priority"]
        if not isinstance(p, int) or isinstance(p, bool) or not (1 <= p <= 5):
            return None, "priority must be an integer 1-5", None
        out["priority"] = p
    if "due_date" in data:
        d = data["due_date"]
        if d is not None:
            dt = parse_ts(d)
            if dt is None:
                return None, "due_date must be ISO-8601", None
            if not partial and dt <= datetime.now(timezone.utc):
                return None, "due_date must be in the future", None
            out["due_date"] = d
        else:
            out["due_date"] = None
    if "tags" in data:
        tags = data["tags"]
        if not isinstance(tags, list) or len(tags) > 10:
            return None, "tags must be a list of <=10 strings", None
        lowered = []
        for t in tags:
            if not isinstance(t, str) or not (1 <= len(t) <= 30):
                return None, "each tag must be 1-30 chars", None
            lowered.append(t.lower())
        if len(set(lowered)) != len(lowered):
            return None, "duplicate tags", "conflict"
        out["tags"] = lowered
    if "project_id" in data:
        out["project_id"] = data["project_id"]
    return out, None, None


def paginate(request):
    q = request.query_params
    try:
        limit = int(q.get("limit", "20"))
        offset = int(q.get("offset", "0"))
    except ValueError:
        return None, None, "limit/offset must be integers"
    if not (1 <= limit <= 100) or offset < 0:
        return None, None, "limit must be 1-100 and offset >= 0"
    return limit, offset, None


# ---------------------------------------------------------------- endpoints

@app.get("/v1/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/projects")
async def create_project(request: Request):
    data, e = await read_json(request)
    if e:
        return e
    fields, msg = validate_project_fields(data)
    if msg:
        return err(422, "validation_error", msg)
    conn = db()
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?)",
        (pid, request.state.key_id, fields["name"], fields.get("description"), now_iso()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    out = project_out(conn, row)
    conn.close()
    return JSONResponse(status_code=201, content=out)


@app.get("/v1/projects")
async def list_projects(request: Request):
    limit, offset, msg = paginate(request)
    if msg:
        return err(422, "validation_error", msg)
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM projects WHERE key_id=?", (request.state.key_id,)).fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM projects WHERE key_id=? ORDER BY created_at DESC, id ASC LIMIT ? OFFSET ?",
        (request.state.key_id, limit, offset),
    ).fetchall()
    data = [project_out(conn, r) for r in rows]
    conn.close()
    return {"data": data, "pagination": {"total": total, "limit": limit, "offset": offset}}


def get_owned(conn, table, rid, key_id):
    return conn.execute(f"SELECT * FROM {table} WHERE id=? AND key_id=?", (rid, key_id)).fetchone()


@app.get("/v1/projects/{pid}")
async def get_project(pid: str, request: Request):
    conn = db()
    row = get_owned(conn, "projects", pid, request.state.key_id)
    if not row:
        conn.close()
        return err(404, "not_found", "project not found")
    out = project_out(conn, row)
    conn.close()
    return out


@app.patch("/v1/projects/{pid}")
async def patch_project(pid: str, request: Request):
    data, e = await read_json(request)
    if e:
        return e
    if not data:
        return err(422, "validation_error", "no fields to update")
    fields, msg = validate_project_fields(data, partial=True)
    if msg:
        return err(422, "validation_error", msg)
    if not fields:
        return err(422, "validation_error", "no fields to update")
    conn = db()
    row = get_owned(conn, "projects", pid, request.state.key_id)
    if not row:
        conn.close()
        return err(404, "not_found", "project not found")
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE projects SET {sets} WHERE id=?", (*fields.values(), pid))
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    out = project_out(conn, row)
    conn.close()
    return out


@app.delete("/v1/projects/{pid}")
async def delete_project(pid: str, request: Request):
    conn = db()
    row = get_owned(conn, "projects", pid, request.state.key_id)
    if not row:
        conn.close()
        return err(404, "not_found", "project not found")
    conn.execute("DELETE FROM tasks WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return Response(status_code=204)


@app.post("/v1/projects/{pid}/tasks")
async def create_task(pid: str, request: Request):
    data, e = await read_json(request)
    if e:
        return e
    conn = db()
    proj = get_owned(conn, "projects", pid, request.state.key_id)
    if not proj:
        conn.close()
        return err(404, "not_found", "project not found")
    fields, msg, code = validate_task_fields(data)
    if msg:
        conn.close()
        return err(409 if code == "conflict" else 422, code or "validation_error", msg)
    tid = str(uuid.uuid4())
    ts = now_iso()
    conn.execute(
        "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            tid, request.state.key_id, pid, fields["title"],
            fields.get("status", "todo"), fields.get("priority", 3),
            fields.get("due_date"), json.dumps(fields.get("tags", [])), ts, ts,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    conn.close()
    return JSONResponse(status_code=201, content=task_out(row))


@app.get("/v1/projects/{pid}/tasks")
async def list_tasks(pid: str, request: Request):
    limit, offset, msg = paginate(request)
    if msg:
        return err(422, "validation_error", msg)
    conn = db()
    proj = get_owned(conn, "projects", pid, request.state.key_id)
    if not proj:
        conn.close()
        return err(404, "not_found", "project not found")
    q = request.query_params
    where, args = ["project_id=?"], [pid]
    if "status" in q:
        if q["status"] not in ("todo", "in_progress", "done"):
            conn.close()
            return err(422, "validation_error", "invalid status filter")
        where.append("status=?"); args.append(q["status"])
    if "priority" in q:
        try:
            p = int(q["priority"])
        except ValueError:
            conn.close()
            return err(422, "validation_error", "invalid priority filter")
        if not (1 <= p <= 5):
            conn.close()
            return err(422, "validation_error", "invalid priority filter")
        where.append("priority=?"); args.append(p)
    if "due_before" in q:
        dt = parse_ts(q["due_before"])
        if dt is None:
            conn.close()
            return err(422, "validation_error", "invalid due_before filter")
        where.append("due_date IS NOT NULL AND due_date < ?")
        args.append(dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    rows = conn.execute(
        f"SELECT * FROM tasks WHERE {' AND '.join(where)} ORDER BY created_at DESC, id ASC",
        args,
    ).fetchall()
    if "tag" in q:
        tag = q["tag"]
        rows = [r for r in rows if tag in json.loads(r["tags"])]
    total = len(rows)
    rows = rows[offset : offset + limit]
    conn.close()
    return {"data": [task_out(r) for r in rows], "pagination": {"total": total, "limit": limit, "offset": offset}}


@app.get("/v1/tasks/{tid}")
async def get_task(tid: str, request: Request):
    conn = db()
    row = get_owned(conn, "tasks", tid, request.state.key_id)
    conn.close()
    if not row:
        return err(404, "not_found", "task not found")
    return task_out(row)


@app.patch("/v1/tasks/{tid}")
async def patch_task(tid: str, request: Request):
    data, e = await read_json(request)
    if e:
        return e
    if not data:
        return err(422, "validation_error", "no fields to update")
    fields, msg, code = validate_task_fields(data, partial=True, allow_project=True)
    if msg:
        return err(409 if code == "conflict" else 422, code or "validation_error", msg)
    if not fields:
        return err(422, "validation_error", "no fields to update")
    conn = db()
    row = get_owned(conn, "tasks", tid, request.state.key_id)
    if not row:
        conn.close()
        return err(404, "not_found", "task not found")
    if "status" in fields:
        if row["status"] == "done" and fields["status"] == "todo":
            conn.close()
            return err(422, "validation_error", "a done task can only move back to in_progress")
    if "project_id" in fields:
        proj = get_owned(conn, "projects", fields["project_id"], request.state.key_id)
        if not proj:
            conn.close()
            return err(404, "not_found", "target project not found")
    if "tags" in fields:
        fields["tags"] = json.dumps(fields["tags"])
    sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=?"
    conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*fields.values(), now_iso(), tid))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    conn.close()
    return task_out(row)


@app.delete("/v1/tasks/{tid}")
async def delete_task(tid: str, request: Request):
    conn = db()
    row = get_owned(conn, "tasks", tid, request.state.key_id)
    if not row:
        conn.close()
        return err(404, "not_found", "task not found")
    conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    return Response(status_code=204)


@app.post("/v1/tasks/{tid}/complete")
async def complete_task(tid: str, request: Request):
    conn = db()
    row = get_owned(conn, "tasks", tid, request.state.key_id)
    if not row:
        conn.close()
        return err(404, "not_found", "task not found")
    if row["status"] == "done":
        conn.close()
        return err(422, "validation_error", "task is already done")
    conn.execute("UPDATE tasks SET status='done', updated_at=? WHERE id=?", (now_iso(), tid))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    conn.close()
    return task_out(row)


@app.post("/v1/tasks/bulk")
async def bulk_tasks(request: Request):
    data, e = await read_json(request)
    if e:
        return e
    items = data.get("tasks") if isinstance(data, dict) else None
    if set(data) - {"tasks"} or not isinstance(items, list):
        return err(422, "validation_error", "body must be {'tasks': [...]}")
    if len(items) > 20:
        return err(422, "validation_error", "at most 20 items per bulk request")
    conn = db()
    results = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or "project_id" not in item:
            results.append({"index": i, "status": 422, "error": {"code": "validation_error", "message": "project_id required"}})
            continue
        pid = item["project_id"]
        rest = {k: v for k, v in item.items() if k != "project_id"}
        proj = get_owned(conn, "projects", pid, request.state.key_id)
        if not proj:
            results.append({"index": i, "status": 404, "error": {"code": "not_found", "message": "project not found"}})
            continue
        fields, msg, code = validate_task_fields(rest)
        if msg:
            status = 409 if code == "conflict" else 422
            results.append({"index": i, "status": status, "error": {"code": code or "validation_error", "message": msg}})
            continue
        tid = str(uuid.uuid4())
        ts = now_iso()
        conn.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                tid, request.state.key_id, pid, fields["title"],
                fields.get("status", "todo"), fields.get("priority", 3),
                fields.get("due_date"), json.dumps(fields.get("tags", [])), ts, ts,
            ),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        results.append({"index": i, "status": 201, "task": task_out(row)})
    conn.commit()
    conn.close()
    return JSONResponse(status_code=207, content={"results": results})


@app.get("/v1/stats")
async def stats(request: Request):
    conn = db()
    kid = request.state.key_id
    projects = conn.execute("SELECT COUNT(*) c FROM projects WHERE key_id=?", (kid,)).fetchone()["c"]
    tasks = conn.execute("SELECT COUNT(*) c FROM tasks WHERE key_id=?", (kid,)).fetchone()["c"]
    by_status = {"todo": 0, "in_progress": 0, "done": 0}
    for r in conn.execute("SELECT status, COUNT(*) c FROM tasks WHERE key_id=? GROUP BY status", (kid,)):
        by_status[r["status"]] = r["c"]
    now = now_iso()
    overdue = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE key_id=? AND due_date IS NOT NULL AND due_date < ? AND status != 'done'",
        (kid, now),
    ).fetchone()["c"]
    conn.close()
    return {"projects": projects, "tasks": tasks, "by_status": by_status, "overdue": overdue}


@app.get("/v1/admin/keys")
async def admin_keys(request: Request):
    if request.state.role != "admin":
        return err(403, "forbidden", "admin role required")
    limit_offset = paginate(request)
    if limit_offset[2]:
        return err(422, "validation_error", limit_offset[2])
    limit, offset, _ = limit_offset
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM keys").fetchone()["c"]
    rows = conn.execute(
        "SELECT id, role, created_at, request_count FROM keys ORDER BY created_at DESC, id ASC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return {
        "data": [dict(r) for r in rows],
        "pagination": {"total": total, "limit": limit, "offset": offset},
    }
