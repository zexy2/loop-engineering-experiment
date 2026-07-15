"""SQLite database helpers for TaskFlow."""
import os
import sqlite3

DB_PATH = os.environ.get("TASKFLOW_DB", "taskflow.db")


def connect():
    """Open a new SQLite connection with sensible defaults.

    A fresh connection per operation keeps things thread-safe without a global
    lock, which is fine at this scale.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id            TEXT PRIMARY KEY,
    key_hash      TEXT UNIQUE NOT NULL,
    role          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    key_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id         TEXT PRIMARY KEY,
    key_id     TEXT NOT NULL,
    project_id TEXT NOT NULL,
    title      TEXT NOT NULL,
    status     TEXT NOT NULL,
    priority   INTEGER NOT NULL,
    due_date   TEXT,
    tags       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_key ON projects(key_id);
CREATE INDEX IF NOT EXISTS idx_tasks_key ON tasks(key_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
"""


def init_db():
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
