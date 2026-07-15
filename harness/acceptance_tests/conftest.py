"""Shared fixtures for the hidden acceptance suite.

The suite is black-box: it talks to a live server over HTTP only.
Required env vars (set by run_tests.sh):
    API_BASE    e.g. http://127.0.0.1:8000
    ADMIN_KEY   plain admin API key
    MEMBER_KEY  plain member API key
"""
import os
import uuid

import httpx
import pytest

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")


@pytest.fixture(scope="session")
def admin_key():
    key = os.environ.get("ADMIN_KEY")
    assert key, "ADMIN_KEY env var not set"
    return key


@pytest.fixture(scope="session")
def member_key():
    key = os.environ.get("MEMBER_KEY")
    assert key, "MEMBER_KEY env var not set"
    return key


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE + "/v1", timeout=10.0) as c:
        yield c


def h(key):
    return {"X-API-Key": key}


@pytest.fixture()
def make_project(client, member_key):
    """Create a project owned by the member key; returns the response JSON."""
    created = []

    def _make(name=None, **kwargs):
        body = {"name": name or f"proj-{uuid.uuid4().hex[:8]}", **kwargs}
        r = client.post("/projects", json=body, headers=h(member_key))
        assert r.status_code == 201, f"project create failed: {r.status_code} {r.text}"
        created.append(r.json()["id"])
        return r.json()

    yield _make
    for pid in created:
        client.delete(f"/projects/{pid}", headers=h(member_key))


@pytest.fixture()
def make_task(client, member_key, make_project):
    """Create a task; makes its own project unless project_id is given."""
    def _make(project_id=None, **kwargs):
        pid = project_id or make_project()["id"]
        body = {"title": kwargs.pop("title", f"task-{uuid.uuid4().hex[:8]}"), **kwargs}
        r = client.post(f"/projects/{pid}/tasks", json=body, headers=h(member_key))
        assert r.status_code == 201, f"task create failed: {r.status_code} {r.text}"
        return r.json()

    return _make


def assert_error(resp, status, code):
    """Assert the spec's error envelope."""
    assert resp.status_code == status, f"expected {status}, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "error" in body, f"missing error envelope: {body}"
    assert body["error"].get("code") == code, f"expected code={code}, got {body['error']}"
    assert isinstance(body["error"].get("message"), str) and body["error"]["message"]
