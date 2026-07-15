# SPEC — TaskFlow API v1

Build a Task Manager REST API exactly as described below.

## Stack (mandatory)

- Python 3, **FastAPI**, **SQLite** (file: `taskflow.db`, via the standard
  library `sqlite3` or SQLAlchemy — your choice).
- Server must start with: `uvicorn app.main:app --port 8000`
  (i.e. an `app/` package with `main.py` exposing `app`).
- Provide `requirements.txt`. No Docker needed.

## Conventions

- Base path: `/v1`.
- All request/response bodies are JSON.
- Timestamps: UTC, ISO-8601 with `Z` suffix (e.g. `2026-07-14T09:30:00Z`).
- IDs: server-generated UUIDv4 strings.
- Errors use this envelope, with the listed status codes:

```json
{ "error": { "code": "<machine_code>", "message": "<human text>" } }
```

| Situation | HTTP | error.code |
|---|---|---|
| Missing/unknown API key | 401 | `unauthorized` |
| Key lacks permission | 403 | `forbidden` |
| Resource not found (or belongs to another key) | 404 | `not_found` |
| Validation failure | 422 | `validation_error` |
| Rate limit exceeded | 429 | `rate_limited` |
| Duplicate (see tags) | 409 | `conflict` |

## Authentication

- Every `/v1/*` endpoint requires header `X-API-Key`.
- Keys are seeded by a script you provide: `python -m app.seed` creates two new
  keys (one **admin**, one **member**) and prints them to stdout in exactly this
  format, one per line, nothing else:

  ```
  admin_key=<plain key>
  member_key=<plain key>
  ```

  Running the seed again creates two additional keys (it never wipes data).
- Keys are stored hashed (SHA-256) in the DB. Unknown or missing key → 401.
- Data is **scoped per key**: a key only ever sees and affects its own
  projects/tasks. Cross-key access to an existing resource returns **404**
  (not 403 — do not leak existence).

## Rate limiting

- **60 requests per minute per API key** by default, sliding or fixed window
  (document which in your README).
- The limit must be configurable via the environment variable
  `RATE_LIMIT_PER_MINUTE` (integer; default 60 when unset).
- Exceeding it → 429 with the error envelope **and** headers:
  - `X-RateLimit-Limit: 60`
  - `X-RateLimit-Remaining: <n>`
  - `Retry-After: <seconds>`
- The `GET /v1/health` endpoint is **exempt** and requires no auth.

## Resources

### Project

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | server-generated |
| `name` | string | required, 1–100 chars after trimming whitespace |
| `description` | string | optional, ≤ 500 chars |
| `created_at` | timestamp | server-set |
| `task_counts` | object | `{"todo": n, "in_progress": n, "done": n}` — computed, read-only |

### Task

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | server-generated |
| `project_id` | uuid | required, must be an existing project owned by the caller |
| `title` | string | required, 1–200 chars after trimming |
| `status` | enum | `todo` \| `in_progress` \| `done`; default `todo` |
| `priority` | int | 1–5; default 3 |
| `due_date` | timestamp | optional; if present, must be in the future **at creation time** |
| `tags` | array of strings | ≤ 10 tags; each 1–30 chars, lowercased by the server; duplicates within one task → 409 `conflict` |
| `created_at` / `updated_at` | timestamp | server-set; `updated_at` changes on every modification |

## Endpoints (15)

### System
1. `GET /v1/health` → 200 `{"status":"ok"}`. No auth, no rate limit.

### Projects
2. `POST /v1/projects` → 201, full project body.
3. `GET /v1/projects` → 200, list (see Pagination).
4. `GET /v1/projects/{id}` → 200.
5. `PATCH /v1/projects/{id}` → 200. Only `name`, `description` may change; unknown fields → 422.
6. `DELETE /v1/projects/{id}` → 204. **Cascades**: deletes the project's tasks.

### Tasks
7. `POST /v1/projects/{project_id}/tasks` → 201.
8. `GET /v1/projects/{project_id}/tasks` → 200, list. Filters (combinable):
   `status`, `priority`, `tag` (single tag, exact match), `due_before`
   (ISO timestamp). Invalid filter values → 422.
9. `GET /v1/tasks/{id}` → 200.
10. `PATCH /v1/tasks/{id}` → 200. Mutable: `title`, `status`, `priority`, `due_date`, `tags`, `project_id` (moving between owned projects allowed). Status transition rule: `done` tasks can only go back to `in_progress` (never straight to `todo`); illegal transition → 422.
11. `DELETE /v1/tasks/{id}` → 204.
12. `POST /v1/tasks/{id}/complete` → 200. Sets `status=done`. Completing an already-`done` task → 422 (`validation_error`, message must mention it is already done).

### Bulk & stats
13. `POST /v1/tasks/bulk` → 207 (multi-status). Body: `{"tasks":[...up to 20 task-create objects (each with project_id)...]}`. Response: `{"results":[{"index":0,"status":201,"task":{...}} | {"index":1,"status":422,"error":{...}}, ...]}` — valid items are created even when others fail. More than 20 items → 422 for the whole request.
14. `GET /v1/stats` → 200: `{"projects": n, "tasks": n, "by_status": {...}, "overdue": n}` (`overdue` = tasks with `due_date` in the past and status ≠ `done`).

### Admin
15. `GET /v1/admin/keys` → 200, list of all API keys (id, role, created_at, request_count — **never** the key itself). Requires `role=admin`; member key → 403.

## Pagination (all list endpoints)

- Query params: `limit` (default 20, min 1, max 100), `offset` (default 0, min 0).
- Out-of-range values → 422.
- Response envelope:

```json
{ "data": [...], "pagination": { "total": 57, "limit": 20, "offset": 0 } }
```

- Ordering: `created_at` descending, ties broken by `id` ascending.

## Edge cases that must work (a non-exhaustive reminder)

- Trimming: `"  My project  "` is stored as `"My project"`; a name that is only whitespace → 422.
- `PATCH` with an empty body → 422 (`validation_error`, "no fields to update").
- Unknown JSON fields anywhere → 422.
- Malformed JSON body → 422.
- Malformed UUID in a path → 404 (treated as "no such resource").
- `?limit=0`, `?limit=101`, `?offset=-1` → 422.
- Tag `"URGENT"` and `"urgent"` in the same task are duplicates (server lowercases first) → 409.
- Bulk with 20 valid items → all 201 inside a 207.
- Deleting a project then GETing its tasks by id → 404.

## Deliverables

- `app/` package (FastAPI), `requirements.txt`, `README.md` (setup + run + your
  window choice for rate limiting), `python -m app.seed` as described.
- The server must be stateless across restarts except for the SQLite file.
