"""Rate limiting — PHASE 2.

Run against a server started with RATE_LIMIT_PER_MINUTE=15 and FRESH keys
(run_tests.sh handles this). Kept out of the main suite so the flood doesn't
starve other tests.

Collected only when RL_PHASE=1 is set.
"""
import os

import pytest

from conftest import h

pytestmark = pytest.mark.skipif(
    os.environ.get("RL_PHASE") != "1", reason="rate-limit phase only"
)

LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "15"))


class TestRateLimit:
    def test_remaining_header_counts_down(self, client, member_key):
        r1 = client.get("/projects", headers=h(member_key))
        assert r1.status_code == 200
        rem1 = int(r1.headers["X-RateLimit-Remaining"])
        r2 = client.get("/projects", headers=h(member_key))
        rem2 = int(r2.headers["X-RateLimit-Remaining"])
        assert rem2 == rem1 - 1
        assert r1.headers.get("X-RateLimit-Limit") == str(LIMIT)

    def test_429_with_envelope_and_headers(self, client, member_key):
        last = None
        for _ in range(LIMIT + 5):
            last = client.get("/projects", headers=h(member_key))
            if last.status_code == 429:
                break
        assert last is not None and last.status_code == 429, (
            f"never rate-limited after {LIMIT + 5} requests"
        )
        assert last.json()["error"]["code"] == "rate_limited"
        assert last.headers.get("X-RateLimit-Limit") == str(LIMIT)
        assert last.headers.get("X-RateLimit-Remaining") == "0"
        assert int(last.headers.get("Retry-After", "-1")) >= 0

    def test_health_exempt_while_limited(self, client, member_key):
        # member key is exhausted from the previous test
        r = client.get("/health")
        assert r.status_code == 200

    def test_limit_is_per_key(self, client, admin_key):
        # admin key must have its own untouched budget
        r = client.get("/projects", headers=h(admin_key))
        assert r.status_code == 200, "rate limit leaked across keys"
