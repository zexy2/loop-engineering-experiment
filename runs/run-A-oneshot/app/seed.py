"""Seed script: creates one admin key and one member key, printing them to stdout.

Usage: python -m app.seed
"""

import secrets
import uuid
from datetime import datetime, timezone

from .db import get_conn, init_db
from .main import hash_key, iso_z


def create_key(conn, role: str) -> str:
    plain = secrets.token_hex(24)
    conn.execute(
        "INSERT INTO api_keys (id, key_hash, role, created_at, request_count) "
        "VALUES (?, ?, ?, ?, 0)",
        (str(uuid.uuid4()), hash_key(plain), role,
         iso_z(datetime.now(timezone.utc))),
    )
    return plain


def main() -> None:
    init_db()
    conn = get_conn()
    try:
        admin_key = create_key(conn, "admin")
        member_key = create_key(conn, "member")
        conn.commit()
    finally:
        conn.close()
    print(f"admin_key={admin_key}")
    print(f"member_key={member_key}")


if __name__ == "__main__":
    main()
