"""TaskFlow API v1 — FastAPI application."""

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .db import get_conn, init_db

VALID_STATUSES = ("todo", "in_progress", "done")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}


def error_response(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers or {},
    )


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    if dt.microsecond:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are taken as UTC."""
    if not isinstance(value, str):
        raise ValueError("not a string")
    raw = value.strip()
    if raw.endswith("Z") or raw.endswith("z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Rate limiting (fixed window, in-memory)
# ---------------------------------------------------------------------------

_rate_state: dict[str, list] = {}  # key_id -> [window_index, count]


def rate_limit_per_minute() -> int:
    raw = os.environ.get("RATE_LIMIT_PER_MINUTE")
    if raw is None:
        return 60
    try:
        return int(raw)
    except ValueError:
        return 60


def check_rate_limit(key_id: str) -> dict:
    """Fixed 60-second window keyed to the epoch minute."""
    limit = rate_limit_per_minute()
    now = time.time()
    window = int(now // 60)
    state = _rate_state.get(key_id)
    if state is None or state[0] != window:
        state = [window, 0]
        _rate_state[key_id] = state
    state[1] += 1
    remaining = max(0, limit - state[1])
    headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
    }
    if state[1] > limit:
        retry_after = max(1, int((window + 1) * 60 - now) + 1)
        headers["Retry-After"] = str(retry_after)
        raise ApiError(429, "rate_limited", "Rate limit exceeded.", headers=headers)
    return headers


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def require_key(request: Request, response: Response) -> dict:
    plain = request.headers.get("X-API-Key")
    if not plain:
        raise ApiError(401, "unauthorized", "Missing API key.")
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, role FROM api_keys WHERE key_hash = ?", (hash_key(plain),)
        ).fetchone()
        if row is None:
            raise ApiError(401, "unauthorized", "Unknown API key.")
        conn.execute(
            "UPDATE api_keys SET request_count = request_count + 1 WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    headers = check_rate_limit(row["id"])
    for name, value in headers.items():
        response.headers[name] = value
    return {"id": row["id"], "role": row["role"]}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

async def read_json_object(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise ApiError(422, "validation_error", "Malformed JSON body.")
    if not isinstance(body, dict):
        raise ApiError(422, "validation_error", "Request body must be a JSON object.")
    return body


def reject_unknown_fields(body: dict, allowed: set):
    unknown = set(body.keys()) - allowed
    if unknown:
        raise ApiError(
            422, "validation_error",
            f"Unknown field(s): {', '.join(sorted(unknown))}.",
        )


def validate_name(value) -> str:
    if not isinstance(value, str):
        raise ApiError(422, "validation_error", "name must be a string.")
    trimmed = value.strip()
    if not (1 <= len(trimmed) <= 100):
        raise ApiError(422, "validation_error", "name must be 1-100 characters after trimming.")
    return trimmed


def validate_description(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(422, "validation_error", "description must be a string.")
    if len(value) > 500:
        raise ApiError(422, "validation_error", "description must be at most 500 characters.")
    return value


def validate_title(value) -> str:
    if not isinstance(value, str):
        raise ApiError(422, "validation_error", "title must be a string.")
    trimmed = value.strip()
    if not (1 <= len(trimmed) <= 200):
        raise ApiError(422, "validation_error", "title must be 1-200 characters after trimming.")
    return trimmed


def validate_status(value) -> str:
    if value not in VALID_STATUSES:
        raise ApiError(
            422, "validation_error",
            "status must be one of: todo, in_progress, done.",
        )
    return value


def validate_priority(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(422, "validation_error", "priority must be an integer.")
    if not (1 <= value <= 5):
        raise ApiError(422, "validation_error", "priority must be between 1 and 5.")
    return value


def validate_due_date(value, must_be_future: bool):
    if value is None:
        return None
    try:
        dt = parse_timestamp(value)
    except (ValueError, TypeError):
        raise ApiError(422, "validation_error", "due_date must be an ISO-8601 timestamp.")
    if must_be_future and dt <= now_utc():
        raise ApiError(422, "validation_error", "due_date must be in the future.")
    return iso_z(dt)


def validate_tags(value) -> list:
    if not isinstance(value, list):
        raise ApiError(422, "validation_error", "tags must be an array of strings.")
    if len(value) > 10:
        raise ApiError(422, "validation_error", "tags must contain at most 10 items.")
    result = []
    for tag in value:
        if not isinstance(tag, str):
            raise ApiError(422, "validation_error", "each tag must be a string.")
        lowered = tag.lower()
        if not (1 <= len(lowered) <= 30):
            raise ApiError(422, "validation_error", "each tag must be 1-30 characters.")
        result.append(lowered)
    if len(set(result)) != len(result):
        raise ApiError(409, "conflict", "Duplicate tags within one task are not allowed.")
    return result


def parse_pagination(request: Request) -> tuple:
    def parse_int(name: str, default: int) -> int:
        raw = request.query_params.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ApiError(422, "validation_error", f"{name} must be an integer.")

    limit = parse_int("limit", 20)
    offset = parse_int("offset", 0)
    if not (1 <= limit <= 100):
        raise ApiError(422, "validation_error", "limit must be between 1 and 100.")
    if offset < 0:
        raise ApiError(422, "validation_error", "offset must be at least 0.")
    return limit, offset


def paginated(items: list, limit: int, offset: int) -> dict:
    return {
        "data": items[offset:offset + limit],
        "pagination": {"total": len(items), "limit": limit, "offset": offset},
    }


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def project_body(conn, row) -> dict:
    counts = {"todo": 0, "in_progress": 0, "done": 0}
    for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM tasks WHERE project_id = ? GROUP BY status",
        (row["id"],),
    ):
        counts[r["status"]] = r["n"]
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "created_at": row["created_at"],
        "task_counts": counts,
    }


def task_body(row) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "title": row["title"],
        "status": row["status"],
        "priority": row["priority"],
        "due_date": row["due_date"],
        "tags": json.loads(row["tags"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_project(conn, key_id: str, project_id: str):
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ? AND key_id = ?", (project_id, key_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "not_found", "Project not found.")
    return row


def fetch_task(conn, key_id: str, task_id: str):
    row = conn.execute(
        "SELECT * FROM tasks WHERE id = ? AND key_id = ?", (task_id, key_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "not_found", "Task not found.")
    return row


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="TaskFlow API", version="1.0.0")
init_db()


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return error_response(exc.status, exc.code, exc.message, exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return error_response(422, "validation_error", "Invalid request.")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    codes = {401: "unauthorized", 403: "forbidden", 404: "not_found",
             422: "validation_error", 429: "rate_limited", 409: "conflict"}
    code = codes.get(exc.status_code, "error")
    return error_response(exc.status_code, code, str(exc.detail))


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@app.get("/v1/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@app.post("/v1/projects", status_code=201)
async def create_project(request: Request, key: dict = Depends(require_key)):
    body = await read_json_object(request)
    reject_unknown_fields(body, {"name", "description"})
    if "name" not in body:
        raise ApiError(422, "validation_error", "name is required.")
    name = validate_name(body["name"])
    description = validate_description(body.get("description"))

    conn = get_conn()
    try:
        project_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO projects (id, key_id, name, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, key["id"], name, description, iso_z(now_utc())),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return project_body(conn, row)
    finally:
        conn.close()


@app.get("/v1/projects")
async def list_projects(request: Request, key: dict = Depends(require_key)):
    limit, offset = parse_pagination(request)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM projects WHERE key_id = ? ORDER BY created_at DESC, id ASC",
            (key["id"],),
        ).fetchall()
        return paginated([project_body(conn, r) for r in rows], limit, offset)
    finally:
        conn.close()


@app.get("/v1/projects/{project_id}")
async def get_project(project_id: str, key: dict = Depends(require_key)):
    conn = get_conn()
    try:
        row = fetch_project(conn, key["id"], project_id)
        return project_body(conn, row)
    finally:
        conn.close()


@app.patch("/v1/projects/{project_id}")
async def patch_project(project_id: str, request: Request, key: dict = Depends(require_key)):
    body = await read_json_object(request)
    reject_unknown_fields(body, {"name", "description"})
    if not body:
        raise ApiError(422, "validation_error", "no fields to update")

    conn = get_conn()
    try:
        row = fetch_project(conn, key["id"], project_id)
        name = row["name"]
        description = row["description"]
        if "name" in body:
            name = validate_name(body["name"])
        if "description" in body:
            description = validate_description(body["description"])
        conn.execute(
            "UPDATE projects SET name = ?, description = ? WHERE id = ?",
            (name, description, project_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return project_body(conn, row)
    finally:
        conn.close()


@app.delete("/v1/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, key: dict = Depends(require_key)):
    conn = get_conn()
    try:
        fetch_project(conn, key["id"], project_id)
        conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

TASK_CREATE_FIELDS = {"project_id", "title", "status", "priority", "due_date", "tags"}


def build_new_task(conn, key_id: str, body: dict, project_id: str) -> dict:
    """Validate a task-create body and insert the row. Returns the task body."""
    fetch_project(conn, key_id, project_id)
    if "title" not in body:
        raise ApiError(422, "validation_error", "title is required.")
    title = validate_title(body["title"])
    status = validate_status(body.get("status", "todo"))
    priority = validate_priority(body.get("priority", 3))
    due_date = validate_due_date(body.get("due_date"), must_be_future=True)
    tags = validate_tags(body.get("tags", []))

    task_id = str(uuid.uuid4())
    ts = iso_z(now_utc())
    conn.execute(
        "INSERT INTO tasks (id, key_id, project_id, title, status, priority, "
        "due_date, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, key_id, project_id, title, status, priority, due_date,
         json.dumps(tags), ts, ts),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return task_body(row)


@app.post("/v1/projects/{project_id}/tasks", status_code=201)
async def create_task(project_id: str, request: Request, key: dict = Depends(require_key)):
    body = await read_json_object(request)
    reject_unknown_fields(body, TASK_CREATE_FIELDS)
    if "project_id" in body and body["project_id"] != project_id:
        raise ApiError(422, "validation_error", "project_id in body does not match the URL.")
    conn = get_conn()
    try:
        return build_new_task(conn, key["id"], body, project_id)
    finally:
        conn.close()


@app.get("/v1/projects/{project_id}/tasks")
async def list_tasks(project_id: str, request: Request, key: dict = Depends(require_key)):
    limit, offset = parse_pagination(request)

    status = request.query_params.get("status")
    if status is not None:
        validate_status(status)

    priority = request.query_params.get("priority")
    if priority is not None:
        try:
            priority = int(priority)
        except ValueError:
            raise ApiError(422, "validation_error", "priority filter must be an integer.")
        validate_priority(priority)

    tag = request.query_params.get("tag")
    if tag is not None and not (1 <= len(tag) <= 30):
        raise ApiError(422, "validation_error", "tag filter must be 1-30 characters.")

    due_before = request.query_params.get("due_before")
    if due_before is not None:
        try:
            due_before = parse_timestamp(due_before)
        except (ValueError, TypeError):
            raise ApiError(422, "validation_error", "due_before must be an ISO-8601 timestamp.")

    conn = get_conn()
    try:
        fetch_project(conn, key["id"], project_id)
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC, id ASC",
            (project_id,),
        ).fetchall()
        items = []
        for row in rows:
            if status is not None and row["status"] != status:
                continue
            if priority is not None and row["priority"] != priority:
                continue
            if tag is not None and tag not in json.loads(row["tags"]):
                continue
            if due_before is not None:
                if row["due_date"] is None or parse_timestamp(row["due_date"]) >= due_before:
                    continue
            items.append(task_body(row))
        return paginated(items, limit, offset)
    finally:
        conn.close()


@app.get("/v1/tasks/{task_id}")
async def get_task(task_id: str, key: dict = Depends(require_key)):
    conn = get_conn()
    try:
        return task_body(fetch_task(conn, key["id"], task_id))
    finally:
        conn.close()


@app.patch("/v1/tasks/{task_id}")
async def patch_task(task_id: str, request: Request, key: dict = Depends(require_key)):
    body = await read_json_object(request)
    reject_unknown_fields(body, {"title", "status", "priority", "due_date", "tags", "project_id"})
    if not body:
        raise ApiError(422, "validation_error", "no fields to update")

    conn = get_conn()
    try:
        row = fetch_task(conn, key["id"], task_id)
        updates = {}
        if "title" in body:
            updates["title"] = validate_title(body["title"])
        if "status" in body:
            new_status = validate_status(body["status"])
            if row["status"] == "done" and new_status not in ("done", "in_progress"):
                raise ApiError(
                    422, "validation_error",
                    "A done task can only transition back to in_progress.",
                )
            updates["status"] = new_status
        if "priority" in body:
            updates["priority"] = validate_priority(body["priority"])
        if "due_date" in body:
            updates["due_date"] = validate_due_date(body["due_date"], must_be_future=False)
        if "tags" in body:
            updates["tags"] = json.dumps(validate_tags(body["tags"]))
        if "project_id" in body:
            if not isinstance(body["project_id"], str):
                raise ApiError(422, "validation_error", "project_id must be a string.")
            fetch_project(conn, key["id"], body["project_id"])
            updates["project_id"] = body["project_id"]

        updates["updated_at"] = iso_z(now_utc())
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            (*updates.values(), task_id),
        )
        conn.commit()
        return task_body(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    finally:
        conn.close()


@app.delete("/v1/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, key: dict = Depends(require_key)):
    conn = get_conn()
    try:
        fetch_task(conn, key["id"], task_id)
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()
    return Response(status_code=204)


@app.post("/v1/tasks/{task_id}/complete")
async def complete_task(task_id: str, key: dict = Depends(require_key)):
    conn = get_conn()
    try:
        row = fetch_task(conn, key["id"], task_id)
        if row["status"] == "done":
            raise ApiError(422, "validation_error", "Task is already done.")
        conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ?",
            (iso_z(now_utc()), task_id),
        )
        conn.commit()
        return task_body(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bulk & stats
# ---------------------------------------------------------------------------

@app.post("/v1/tasks/bulk", status_code=207)
async def bulk_create_tasks(request: Request, key: dict = Depends(require_key)):
    body = await read_json_object(request)
    reject_unknown_fields(body, {"tasks"})
    items = body.get("tasks")
    if not isinstance(items, list):
        raise ApiError(422, "validation_error", "tasks must be an array.")
    if len(items) > 20:
        raise ApiError(422, "validation_error", "tasks must contain at most 20 items.")

    conn = get_conn()
    try:
        results = []
        for index, item in enumerate(items):
            try:
                if not isinstance(item, dict):
                    raise ApiError(422, "validation_error", "each task must be a JSON object.")
                reject_unknown_fields(item, TASK_CREATE_FIELDS)
                project_id = item.get("project_id")
                if not isinstance(project_id, str):
                    raise ApiError(422, "validation_error", "project_id is required.")
                task = build_new_task(conn, key["id"], item, project_id)
                results.append({"index": index, "status": 201, "task": task})
            except ApiError as exc:
                results.append({
                    "index": index,
                    "status": exc.status,
                    "error": {"code": exc.code, "message": exc.message},
                })
        return {"results": results}
    finally:
        conn.close()


@app.get("/v1/stats")
async def stats(key: dict = Depends(require_key)):
    conn = get_conn()
    try:
        projects = conn.execute(
            "SELECT COUNT(*) AS n FROM projects WHERE key_id = ?", (key["id"],)
        ).fetchone()["n"]
        by_status = {"todo": 0, "in_progress": 0, "done": 0}
        total_tasks = 0
        overdue = 0
        now = now_utc()
        for row in conn.execute(
            "SELECT status, due_date FROM tasks WHERE key_id = ?", (key["id"],)
        ):
            total_tasks += 1
            by_status[row["status"]] += 1
            if (row["due_date"] is not None and row["status"] != "done"
                    and parse_timestamp(row["due_date"]) < now):
                overdue += 1
        return {
            "projects": projects,
            "tasks": total_tasks,
            "by_status": by_status,
            "overdue": overdue,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.get("/v1/admin/keys")
async def admin_keys(request: Request, key: dict = Depends(require_key)):
    if key["role"] != "admin":
        raise ApiError(403, "forbidden", "Admin role required.")
    limit, offset = parse_pagination(request)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, role, created_at, request_count FROM api_keys "
            "ORDER BY created_at DESC, id ASC"
        ).fetchall()
        items = [
            {"id": r["id"], "role": r["role"], "created_at": r["created_at"],
             "request_count": r["request_count"]}
            for r in rows
        ]
        return paginated(items, limit, offset)
    finally:
        conn.close()
