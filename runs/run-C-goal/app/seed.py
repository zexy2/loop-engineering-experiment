"""Seed script: create one admin key and one member key.

Usage:
    python -m app.seed

Prints exactly two lines to stdout:
    admin_key=<plain key>
    member_key=<plain key>

Running it again creates two additional keys; it never wipes existing data.
"""
import hashlib
import secrets
import uuid

from .db import connect, init_db
from .validation import now_iso


def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def generate_key(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def create_key(conn, role: str, prefix: str) -> str:
    plain = generate_key(prefix)
    conn.execute(
        "INSERT INTO api_keys (id, key_hash, role, created_at, request_count) "
        "VALUES (?, ?, ?, ?, 0)",
        (str(uuid.uuid4()), hash_key(plain), role, now_iso()),
    )
    return plain


def main():
    init_db()
    conn = connect()
    try:
        admin_plain = create_key(conn, "admin", "admin")
        member_plain = create_key(conn, "member", "member")
        conn.commit()
    finally:
        conn.close()

    print(f"admin_key={admin_plain}")
    print(f"member_key={member_plain}")


if __name__ == "__main__":
    main()
