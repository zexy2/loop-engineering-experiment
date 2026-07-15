"""Seed script: creates one admin and one member key, prints them."""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from .main import db, init_db


def main():
    init_db()
    conn = db()
    keys = {}
    for role in ("admin", "member"):
        plain = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO keys (id, key_hash, role, created_at, request_count) VALUES (?,?,?,?,0)",
            (
                str(uuid.uuid4()),
                hashlib.sha256(plain.encode()).hexdigest(),
                role,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )
        keys[role] = plain
    conn.commit()
    conn.close()
    print(f"admin_key={keys['admin']}")
    print(f"member_key={keys['member']}")


if __name__ == "__main__":
    main()
