"""TaskFlow API v1 — FastAPI application.

Run with:  uvicorn app.main:app --port 8000
"""
import json
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .db import connect, init_db
from .errors import ApiError, envelope, error_response
from .ratelimit import limiter
from .seed import hash_key
from .validation import (
    now_iso,
    parse_pagination,
    parse_task_filters,
    validate_project_create,
    validate_project_patch,
    validate_task_create,
    validate_task_patch,
)

app = FastAPI(title="TaskFlow API", version="1.0")

init_db()


# -----------------------------------------------------------------------------
# Auth + rate limiting middleware
# -----------------------------------------------------------------------------
@app.middleware("http")
async def gate(request: Request, call_next):
    path = request.url.path

    # Health check is fully exempt: no auth, no rate limit.
    if path == "/v1/health":
        return await call_next(request)

    # Anything outside the versioned API is passed through untouched.
    if not path.startswith("/v1"):
        return await call_next(request)

    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return error_response(401, "unauthorized", "missing API key")

    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ?", (hash_key(api_key),)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return error_response(401, "unauthorized", "invalid API key")

    allowed, limit, remaining, retry_after = limiter.check(row["id"])
    if not allowed:
        return error_response(
            429,
            "rate_limited",
            "rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after),
            },
        )

    conn = connect()
    try:
        conn.execute(
            "UPDATE api_keys SET request_count = request_count + 1 WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    request.state.key_id = row["id"]
    request.state.key_role = row["role"]

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


# -----------------------------------------------------------------------------
# Exception handlers — everything renders the spec error envelope
# -----------------------------------------------------------------------------
@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError):
    return error_response(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return error_response(422, "validation_error", "invalid request")


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    mapping = {
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        422: "validation_error",
        429: "rate_limited",
        409: "conflict",
    }
    code = mapping.get(exc.status_code, "error")
    message = exc.detail if isinstance(exc.detail, str) else code
    return error_response(exc.status_code, code, message)


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    return error_response(500, "internal_error", "internal server error")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
async def read_json_body(request: Request):
    raw = await request.body()
    if not raw or raw.strip() == b"":
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ApiError(422, "validation_error", "malformed JSON body")


def key_id(request: Request) -> str:
    return request.state.key_id


def serialize_project(conn, row) -> dict:
    counts = {"todo": 0, "in_progress": 0, "done": 0}
    for r in conn.execute(
        "SELECT status, COUNT(*) AS c FROM tasks WHERE project_id = ? AND key_id = ? GROUP BY status",
        (row["id"], row["key_id"]),
    ):
        counts[r["status"]] = r["c"]
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "created_at": row["created_at"],
        "task_counts": counts,
    }


def serialize_task(row) -> dict:
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


def get_project_row(conn, kid, project_id):
    return conn.execute(
        "SELECT * FROM projects WHERE id = ? AND key_id = ?", (project_id, kid)
    ).fetchone()


def get_task_row(conn, kid, task_id):
    return conn.execute(
        "SELECT * FROM tasks WHERE id = ? AND key_id = ?", (task_id, kid)
    ).fetchone()


def insert_task(conn, kid, prepared, project_error_status):
    """Create a task after verifying the referenced project is owned."""
    proj = get_project_row(conn, kid, prepared["project_id"])
    if proj is None:
        code = "not_found" if project_error_status == 404 else "validation_error"
        raise ApiError(project_error_status, code, "project not found")

    task_id = str(uuid.uuid4())
    ts = now_iso()
    conn.execute(
        "INSERT INTO tasks (id, key_id, project_id, title, status, priority, "
        "due_date, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id,
            kid,
            prepared["project_id"],
            prepared["title"],
            prepared["status"],
            prepared["priority"],
            prepared["due_date"],
            json.dumps(prepared["tags"]),
            ts,
            ts,
        ),
    )
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def sort_tasks(rows):
    """created_at descending, ties broken by id ascending."""
    rows = list(rows)
    rows.sort(key=lambda r: r["id"])
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows


# -----------------------------------------------------------------------------
# System
# -----------------------------------------------------------------------------
@app.get("/v1/health")
async def health():
    return {"status": "ok"}


# -----------------------------------------------------------------------------
# Projects
# -----------------------------------------------------------------------------
@app.post("/v1/projects", status_code=201)
async def create_project(request: Request):
    data = await read_json_body(request)
    fields = validate_project_create(data)
    kid = key_id(request)
    conn = connect()
    try:
        pid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO projects (id, key_id, name, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (pid, kid, fields["name"], fields["description"], now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        return JSONResponse(status_code=201, content=serialize_project(conn, row))
    finally:
        conn.close()


@app.get("/v1/projects")
async def list_projects(request: Request):
    limit, offset = parse_pagination(request.query_params)
    kid = key_id(request)
    conn = connect()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM projects WHERE key_id = ?", (kid,)
        ).fetchone()["c"]
        rows = conn.execute(
            "SELECT * FROM projects WHERE key_id = ? "
            "ORDER BY created_at DESC, id ASC LIMIT ? OFFSET ?",
            (kid, limit, offset),
        ).fetchall()
        data = [serialize_project(conn, r) for r in rows]
        return {
            "data": data,
            "pagination": {"total": total, "limit": limit, "offset": offset},
        }
    finally:
        conn.close()


@app.get("/v1/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    kid = key_id(request)
    conn = connect()
    try:
        row = get_project_row(conn, kid, project_id)
        if row is None:
            raise ApiError(404, "not_found", "project not found")
        return serialize_project(conn, row)
    finally:
        conn.close()


@app.patch("/v1/projects/{project_id}")
async def patch_project(request: Request, project_id: str):
    data = await read_json_body(request)
    updates = validate_project_patch(data)
    kid = key_id(request)
    conn = connect()
    try:
        row = get_project_row(conn, kid, project_id)
        if row is None:
            raise ApiError(404, "not_found", "project not found")
        sets = ", ".join(f"{col} = ?" for col in updates)
        params = list(updates.values()) + [project_id, kid]
        conn.execute(
            f"UPDATE projects SET {sets} WHERE id = ? AND key_id = ?", params
        )
        conn.commit()
        row = get_project_row(conn, kid, project_id)
        return serialize_project(conn, row)
    finally:
        conn.close()


@app.delete("/v1/projects/{project_id}", status_code=204)
async def delete_project(request: Request, project_id: str):
    kid = key_id(request)
    conn = connect()
    try:
        row = get_project_row(conn, kid, project_id)
        if row is None:
            raise ApiError(404, "not_found", "project not found")
        conn.execute(
            "DELETE FROM tasks WHERE project_id = ? AND key_id = ?", (project_id, kid)
        )
        conn.execute(
            "DELETE FROM projects WHERE id = ? AND key_id = ?", (project_id, kid)
        )
        conn.commit()
        return Response(status_code=204)
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Tasks
# -----------------------------------------------------------------------------
@app.post("/v1/projects/{project_id}/tasks", status_code=201)
async def create_task(request: Request, project_id: str):
    data = await read_json_body(request)
    prepared = validate_task_create(data, require_project_id=False)
    # project_id comes from the path for this endpoint.
    prepared["project_id"] = project_id
    kid = key_id(request)
    conn = connect()
    try:
        row = insert_task(conn, kid, prepared, project_error_status=404)
        conn.commit()
        return JSONResponse(status_code=201, content=serialize_task(row))
    finally:
        conn.close()


@app.get("/v1/projects/{project_id}/tasks")
async def list_tasks(request: Request, project_id: str):
    limit, offset = parse_pagination(request.query_params)
    filters = parse_task_filters(request.query_params)
    kid = key_id(request)
    conn = connect()
    try:
        project = get_project_row(conn, kid, project_id)
        if project is None:
            raise ApiError(404, "not_found", "project not found")

        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND key_id = ?",
            (project_id, kid),
        ).fetchall()

        def keep(row):
            if "status" in filters and row["status"] != filters["status"]:
                return False
            if "priority" in filters and row["priority"] != filters["priority"]:
                return False
            if "tag" in filters and filters["tag"] not in json.loads(row["tags"]):
                return False
            if "due_before" in filters:
                if row["due_date"] is None or row["due_date"] >= filters["due_before"]:
                    return False
            return True

        filtered = sort_tasks([r for r in rows if keep(r)])
        total = len(filtered)
        page = filtered[offset : offset + limit]
        return {
            "data": [serialize_task(r) for r in page],
            "pagination": {"total": total, "limit": limit, "offset": offset},
        }
    finally:
        conn.close()


@app.get("/v1/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    kid = key_id(request)
    conn = connect()
    try:
        row = get_task_row(conn, kid, task_id)
        if row is None:
            raise ApiError(404, "not_found", "task not found")
        return serialize_task(row)
    finally:
        conn.close()


@app.patch("/v1/tasks/{task_id}")
async def patch_task(request: Request, task_id: str):
    data = await read_json_body(request)
    updates = validate_task_patch(data)
    kid = key_id(request)
    conn = connect()
    try:
        row = get_task_row(conn, kid, task_id)
        if row is None:
            raise ApiError(404, "not_found", "task not found")

        # Status transition rule: a done task may only move to in_progress.
        if "status" in updates:
            if row["status"] == "done" and updates["status"] == "todo":
                raise ApiError(
                    422,
                    "validation_error",
                    "a done task can only move back to in_progress, not todo",
                )

        # Moving to another project requires it to be owned by the caller.
        if "project_id" in updates:
            target = get_project_row(conn, kid, updates["project_id"])
            if target is None:
                raise ApiError(422, "validation_error", "project not found")

        columns = dict(updates)
        if "tags" in columns:
            columns["tags"] = json.dumps(columns["tags"])
        columns["updated_at"] = now_iso()

        sets = ", ".join(f"{col} = ?" for col in columns)
        params = list(columns.values()) + [task_id, kid]
        conn.execute(f"UPDATE tasks SET {sets} WHERE id = ? AND key_id = ?", params)
        conn.commit()

        row = get_task_row(conn, kid, task_id)
        return serialize_task(row)
    finally:
        conn.close()


@app.delete("/v1/tasks/{task_id}", status_code=204)
async def delete_task(request: Request, task_id: str):
    kid = key_id(request)
    conn = connect()
    try:
        row = get_task_row(conn, kid, task_id)
        if row is None:
            raise ApiError(404, "not_found", "task not found")
        conn.execute("DELETE FROM tasks WHERE id = ? AND key_id = ?", (task_id, kid))
        conn.commit()
        return Response(status_code=204)
    finally:
        conn.close()


@app.post("/v1/tasks/{task_id}/complete")
async def complete_task(request: Request, task_id: str):
    kid = key_id(request)
    conn = connect()
    try:
        row = get_task_row(conn, kid, task_id)
        if row is None:
            raise ApiError(404, "not_found", "task not found")
        if row["status"] == "done":
            raise ApiError(422, "validation_error", "task is already done")
        conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ? AND key_id = ?",
            (now_iso(), task_id, kid),
        )
        conn.commit()
        row = get_task_row(conn, kid, task_id)
        return serialize_task(row)
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Bulk & stats
# -----------------------------------------------------------------------------
@app.post("/v1/tasks/bulk")
async def bulk_create_tasks(request: Request):
    data = await read_json_body(request)
    if not isinstance(data, dict) or "tasks" not in data:
        raise ApiError(422, "validation_error", "body must contain a 'tasks' array")
    extra = set(data.keys()) - {"tasks"}
    if extra:
        raise ApiError(422, "validation_error", "unknown field(s): " + ", ".join(sorted(extra)))
    tasks = data["tasks"]
    if not isinstance(tasks, list):
        raise ApiError(422, "validation_error", "'tasks' must be an array")
    if len(tasks) > 20:
        raise ApiError(422, "validation_error", "at most 20 tasks per bulk request")

    kid = key_id(request)
    conn = connect()
    results = []
    try:
        for index, item in enumerate(tasks):
            try:
                prepared = validate_task_create(item, require_project_id=True)
                row = insert_task(conn, kid, prepared, project_error_status=422)
                results.append(
                    {"index": index, "status": 201, "task": serialize_task(row)}
                )
            except ApiError as exc:
                results.append(
                    {
                        "index": index,
                        "status": exc.status,
                        "error": envelope(exc.code, exc.message)["error"],
                    }
                )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse(status_code=207, content={"results": results})


@app.get("/v1/stats")
async def stats(request: Request):
    kid = key_id(request)
    conn = connect()
    try:
        projects = conn.execute(
            "SELECT COUNT(*) AS c FROM projects WHERE key_id = ?", (kid,)
        ).fetchone()["c"]
        task_total = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE key_id = ?", (kid,)
        ).fetchone()["c"]

        by_status = {"todo": 0, "in_progress": 0, "done": 0}
        for r in conn.execute(
            "SELECT status, COUNT(*) AS c FROM tasks WHERE key_id = ? GROUP BY status",
            (kid,),
        ):
            by_status[r["status"]] = r["c"]

        overdue = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE key_id = ? AND status != 'done' "
            "AND due_date IS NOT NULL AND due_date < ?",
            (kid, now_iso()),
        ).fetchone()["c"]

        return {
            "projects": projects,
            "tasks": task_total,
            "by_status": by_status,
            "overdue": overdue,
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Admin
# -----------------------------------------------------------------------------
@app.get("/v1/admin/keys")
async def admin_keys(request: Request):
    if request.state.key_role != "admin":
        raise ApiError(403, "forbidden", "admin role required")
    limit, offset = parse_pagination(request.query_params)
    conn = connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM api_keys").fetchone()["c"]
        rows = conn.execute(
            "SELECT id, role, created_at, request_count FROM api_keys "
            "ORDER BY created_at DESC, id ASC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        data = [
            {
                "id": r["id"],
                "role": r["role"],
                "created_at": r["created_at"],
                "request_count": r["request_count"],
            }
            for r in rows
        ]
        return {
            "data": data,
            "pagination": {"total": total, "limit": limit, "offset": offset},
        }
    finally:
        conn.close()
