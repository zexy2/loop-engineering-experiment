"""SQLite helpers for TaskFlow."""

import os
import sqlite3

DB_PATH = os.environ.get("TASKFLOW_DB", "taskflow.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id            TEXT PRIMARY KEY,
    key_hash      TEXT NOT NULL UNIQUE,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    created_at    TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    key_id      TEXT NOT NULL REFERENCES api_keys(id),
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id         TEXT PRIMARY KEY,
    key_id     TEXT NOT NULL REFERENCES api_keys(id),
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('todo', 'in_progress', 'done')),
    priority   INTEGER NOT NULL,
    due_date   TEXT,
    tags       TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_key ON projects(key_id);
CREATE INDEX IF NOT EXISTS idx_tasks_key ON tasks(key_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
