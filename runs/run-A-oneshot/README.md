# TaskFlow API v1

A task manager REST API built with FastAPI and SQLite.

## Setup

```bash
pip install -r requirements.txt
```

## Seed API keys

```bash
python -m app.seed
```

Prints two fresh keys (one admin, one member):

```
admin_key=<plain key>
member_key=<plain key>
```

Keys are stored SHA-256-hashed in `taskflow.db`. Running the seed again adds
two more keys; it never wipes existing data.

## Run

```bash
uvicorn app.main:app --port 8000
```

## Authentication

Every `/v1/*` endpoint except `GET /v1/health` requires the `X-API-Key`
header. Data is scoped per key — a key only sees its own projects and tasks.

## Rate limiting

**Fixed window**: each API key gets `RATE_LIMIT_PER_MINUTE` requests
(default **60**) per clock minute (epoch-aligned 60-second windows). The
counter resets at the top of each minute. Exceeding the limit returns 429
with `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `Retry-After` headers.
`GET /v1/health` is exempt.

```bash
RATE_LIMIT_PER_MINUTE=120 uvicorn app.main:app --port 8000
```

Note: the rate limit counter is in-memory (resets on server restart), as the
only state that must survive restarts is the SQLite file.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/health` | no auth |
| POST | `/v1/projects` | create project |
| GET | `/v1/projects` | list (paginated) |
| GET | `/v1/projects/{id}` | |
| PATCH | `/v1/projects/{id}` | `name`, `description` only |
| DELETE | `/v1/projects/{id}` | cascades to tasks |
| POST | `/v1/projects/{id}/tasks` | create task |
| GET | `/v1/projects/{id}/tasks` | filters: `status`, `priority`, `tag`, `due_before` |
| GET | `/v1/tasks/{id}` | |
| PATCH | `/v1/tasks/{id}` | |
| DELETE | `/v1/tasks/{id}` | |
| POST | `/v1/tasks/{id}/complete` | |
| POST | `/v1/tasks/bulk` | up to 20 items, 207 multi-status |
| GET | `/v1/stats` | |
| GET | `/v1/admin/keys` | admin role only |

Pagination on list endpoints: `?limit=` (1-100, default 20), `?offset=`
(≥0, default 0). Responses use `{"data": [...], "pagination": {...}}`.
