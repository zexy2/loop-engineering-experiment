# TaskFlow API v1

A Task Manager REST API built with **FastAPI** and **SQLite** (via the standard
library `sqlite3`).

## Requirements

- Python 3.9+
- Dependencies in `requirements.txt`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Seed API keys

Keys are required for every `/v1/*` endpoint (except `/v1/health`). Create one
admin key and one member key:

```bash
python -m app.seed
```

This prints exactly two lines:

```
admin_key=<plain key>
member_key=<plain key>
```

Keys are shown **only once** — they are stored SHA-256–hashed in the database.
Run the command again to mint two more keys; it never wipes existing data.

## Run

```bash
uvicorn app.main:app --port 8000
```

Then send the key in the `X-API-Key` header:

```bash
curl -s localhost:8000/v1/projects \
  -H "X-API-Key: <your key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "My project"}'
```

## Conventions

- Base path: `/v1`. All bodies are JSON.
- Timestamps are UTC ISO-8601 with a `Z` suffix (e.g. `2026-07-14T09:30:00Z`).
- IDs are server-generated UUIDv4 strings.
- Data is **scoped per API key**: a key only sees and affects its own projects
  and tasks. Accessing another key's resource returns `404` (existence is never
  leaked).
- Errors use the envelope:

  ```json
  { "error": { "code": "<machine_code>", "message": "<human text>" } }
  ```

## Rate limiting

- **Sliding window**: 60 requests per rolling 60-second window, per API key.
- Configurable via the `RATE_LIMIT_PER_MINUTE` environment variable (integer;
  defaults to 60 when unset or invalid).
- On exceed: `429` with the error envelope and headers `X-RateLimit-Limit`,
  `X-RateLimit-Remaining`, `Retry-After`. These rate-limit headers are also
  attached to successful `/v1/*` responses.
- `GET /v1/health` is exempt (no auth, no rate limit).
- Rate-limit state is kept in memory and is intentionally not persisted across
  restarts; the SQLite file (`taskflow.db`) is the only durable state.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `RATE_LIMIT_PER_MINUTE` | `60` | Requests allowed per key per 60s window |
| `TASKFLOW_DB` | `taskflow.db` | SQLite database file path |

## Endpoints

| # | Method | Path | Notes |
|---|---|---|---|
| 1 | GET | `/v1/health` | No auth, no rate limit |
| 2 | POST | `/v1/projects` | Create project |
| 3 | GET | `/v1/projects` | List (paginated) |
| 4 | GET | `/v1/projects/{id}` | Fetch one |
| 5 | PATCH | `/v1/projects/{id}` | Update `name`/`description` |
| 6 | DELETE | `/v1/projects/{id}` | Cascades to its tasks |
| 7 | POST | `/v1/projects/{project_id}/tasks` | Create task |
| 8 | GET | `/v1/projects/{project_id}/tasks` | List with filters |
| 9 | GET | `/v1/tasks/{id}` | Fetch one |
| 10 | PATCH | `/v1/tasks/{id}` | Update mutable fields |
| 11 | DELETE | `/v1/tasks/{id}` | Delete |
| 12 | POST | `/v1/tasks/{id}/complete` | Mark done |
| 13 | POST | `/v1/tasks/bulk` | Up to 20; returns 207 multi-status |
| 14 | GET | `/v1/stats` | Aggregate counts |
| 15 | GET | `/v1/admin/keys` | Admin only |

### Task list filters (endpoint 8)

Combinable query params: `status`, `priority`, `tag` (single exact tag),
`due_before` (ISO timestamp). Invalid values → `422`.

### Pagination (all list endpoints)

Query params `limit` (default 20, 1–100) and `offset` (default 0, ≥ 0).
Out-of-range values → `422`. Ordering is `created_at` descending, ties broken by
`id` ascending. Response envelope:

```json
{ "data": [ ... ], "pagination": { "total": 57, "limit": 20, "offset": 0 } }
```

## Notes on behavior

- Task `due_date` must be in the future **at creation time**. On `PATCH` the
  future constraint is not enforced (so a task can be made overdue).
- A `done` task can only transition back to `in_progress`, never straight to
  `todo` (illegal transition → `422`).
- Tags are lowercased by the server; duplicate tags within one task → `409`.
- Referencing a non-existent/foreign project by id: via the path
  (`POST /v1/projects/{project_id}/tasks`) → `404`; via a request body
  (bulk create, task `project_id` on patch) → `422`.
```
