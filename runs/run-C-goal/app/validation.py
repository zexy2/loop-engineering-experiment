"""Request validation and value normalization.

All validation raises ApiError with the correct status/code so the exception
handler can render the spec's error envelope. We validate manually (rather than
relying on Pydantic) to control the exact error format and to reject unknown
fields everywhere.
"""
from datetime import datetime, timezone

from .errors import ApiError

STATUSES = ("todo", "in_progress", "done")

PROJECT_CREATE_FIELDS = {"name", "description"}
PROJECT_PATCH_FIELDS = {"name", "description"}
TASK_CREATE_FIELDS = {"project_id", "title", "status", "priority", "due_date", "tags"}
TASK_PATCH_FIELDS = {"title", "status", "priority", "due_date", "tags", "project_id"}


def _err(message, status=422, code="validation_error"):
    return ApiError(status, code, message)


# --- timestamps ---------------------------------------------------------------

def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return format_dt(now_dt())


def format_dt(dt: datetime) -> str:
    """Format a UTC datetime as ISO-8601 with a Z suffix, second precision."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value, field="due_date") -> datetime:
    if not isinstance(value, str):
        raise _err(f"{field} must be an ISO-8601 timestamp string")
    s = value.strip()
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise _err(f"{field} is not a valid ISO-8601 timestamp")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --- field validators ---------------------------------------------------------

def _check_unknown(data, allowed):
    extra = set(data.keys()) - allowed
    if extra:
        names = ", ".join(sorted(extra))
        raise _err(f"unknown field(s): {names}")


def _validate_name(value):
    if not isinstance(value, str):
        raise _err("name must be a string")
    trimmed = value.strip()
    if len(trimmed) < 1:
        raise _err("name must not be empty or whitespace")
    if len(trimmed) > 100:
        raise _err("name must be at most 100 characters")
    return trimmed


def _validate_description(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise _err("description must be a string")
    if len(value) > 500:
        raise _err("description must be at most 500 characters")
    return value


def _validate_title(value):
    if not isinstance(value, str):
        raise _err("title must be a string")
    trimmed = value.strip()
    if len(trimmed) < 1:
        raise _err("title must not be empty or whitespace")
    if len(trimmed) > 200:
        raise _err("title must be at most 200 characters")
    return trimmed


def _validate_status(value):
    if value not in STATUSES:
        raise _err("status must be one of: todo, in_progress, done")
    return value


def _validate_priority(value):
    # Reject booleans (which are ints in Python) and non-integers.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _err("priority must be an integer between 1 and 5")
    if value < 1 or value > 5:
        raise _err("priority must be between 1 and 5")
    return value


def _validate_tags(value):
    if not isinstance(value, list):
        raise _err("tags must be an array of strings")
    if len(value) > 10:
        raise _err("tags may contain at most 10 items")
    seen = set()
    out = []
    for tag in value:
        if not isinstance(tag, str):
            raise _err("each tag must be a string")
        normalized = tag.lower()
        if len(normalized) < 1 or len(normalized) > 30:
            raise _err("each tag must be between 1 and 30 characters")
        if normalized in seen:
            raise ApiError(409, "conflict", f"duplicate tag: {normalized}")
        seen.add(normalized)
        out.append(normalized)
    return out


# --- resource validators ------------------------------------------------------

def validate_project_create(data):
    if not isinstance(data, dict):
        raise _err("request body must be a JSON object")
    _check_unknown(data, PROJECT_CREATE_FIELDS)
    if "name" not in data:
        raise _err("name is required")
    name = _validate_name(data["name"])
    description = _validate_description(data.get("description"))
    return {"name": name, "description": description}


def validate_project_patch(data):
    if not isinstance(data, dict):
        raise _err("request body must be a JSON object")
    if len(data) == 0:
        raise _err("no fields to update")
    _check_unknown(data, PROJECT_PATCH_FIELDS)
    updates = {}
    if "name" in data:
        updates["name"] = _validate_name(data["name"])
    if "description" in data:
        updates["description"] = _validate_description(data["description"])
    return updates


def validate_task_create(data, require_project_id=True):
    """Validate a task-create object.

    Returns a dict of prepared fields. project_id ownership is checked by the
    caller (it needs DB access and the error status differs by context).
    """
    if not isinstance(data, dict):
        raise _err("request body must be a JSON object")
    _check_unknown(data, TASK_CREATE_FIELDS)

    if "title" not in data:
        raise _err("title is required")

    prepared = {
        "title": _validate_title(data["title"]),
        "status": "todo",
        "priority": 3,
        "due_date": None,
        "tags": [],
    }

    if require_project_id:
        if "project_id" not in data or not isinstance(data["project_id"], str):
            raise _err("project_id is required")
        prepared["project_id"] = data["project_id"]

    if "status" in data:
        prepared["status"] = _validate_status(data["status"])
    if "priority" in data:
        prepared["priority"] = _validate_priority(data["priority"])
    if "tags" in data:
        prepared["tags"] = _validate_tags(data["tags"])
    if "due_date" in data and data["due_date"] is not None:
        dt = parse_timestamp(data["due_date"])
        if dt <= now_dt():
            raise _err("due_date must be in the future")
        prepared["due_date"] = format_dt(dt)

    return prepared


def validate_task_patch(data):
    if not isinstance(data, dict):
        raise _err("request body must be a JSON object")
    if len(data) == 0:
        raise _err("no fields to update")
    _check_unknown(data, TASK_PATCH_FIELDS)

    updates = {}
    if "title" in data:
        updates["title"] = _validate_title(data["title"])
    if "status" in data:
        updates["status"] = _validate_status(data["status"])
    if "priority" in data:
        updates["priority"] = _validate_priority(data["priority"])
    if "tags" in data:
        updates["tags"] = _validate_tags(data["tags"])
    if "project_id" in data:
        if not isinstance(data["project_id"], str):
            raise _err("project_id must be a string")
        updates["project_id"] = data["project_id"]
    if "due_date" in data:
        if data["due_date"] is None:
            updates["due_date"] = None
        else:
            # On update the future constraint no longer applies (e.g. so a task
            # can be made overdue); we only require a valid timestamp.
            updates["due_date"] = format_dt(parse_timestamp(data["due_date"]))
    return updates


# --- query params -------------------------------------------------------------

def parse_pagination(params):
    def parse_int(name, default):
        raw = params.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise _err(f"{name} must be an integer")

    limit = parse_int("limit", 20)
    offset = parse_int("offset", 0)
    if limit < 1 or limit > 100:
        raise _err("limit must be between 1 and 100")
    if offset < 0:
        raise _err("offset must be >= 0")
    return limit, offset


def parse_task_filters(params):
    filters = {}
    if "status" in params:
        filters["status"] = _validate_status(params.get("status"))
    if "priority" in params:
        raw = params.get("priority")
        try:
            priority = int(raw)
        except ValueError:
            raise _err("priority filter must be an integer")
        filters["priority"] = _validate_priority(priority)
    if "tag" in params:
        tag = params.get("tag").lower()
        if len(tag) < 1 or len(tag) > 30:
            raise _err("tag filter must be between 1 and 30 characters")
        filters["tag"] = tag
    if "due_before" in params:
        filters["due_before"] = format_dt(parse_timestamp(params.get("due_before"), "due_before"))
    return filters
