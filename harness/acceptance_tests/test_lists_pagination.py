"""Pagination, filters, ordering."""
import uuid
from datetime import datetime, timedelta, timezone

from conftest import h, assert_error


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestPaginationEnvelope:
    def test_envelope_shape(self, client, member_key, make_project):
        make_project()
        r = client.get("/projects", headers=h(member_key))
        assert r.status_code == 200
        body = r.json()
        assert "data" in body and isinstance(body["data"], list)
        pg = body["pagination"]
        assert set(pg.keys()) >= {"total", "limit", "offset"}
        assert pg["limit"] == 20 and pg["offset"] == 0

    def test_limit_and_offset_respected(self, client, member_key, make_project):
        for i in range(5):
            make_project(name=f"pg-{i}")
        r = client.get("/projects", params={"limit": 2, "offset": 1}, headers=h(member_key))
        body = r.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["limit"] == 2
        assert body["pagination"]["offset"] == 1
        assert body["pagination"]["total"] >= 5

    def test_limit_bounds(self, client, member_key):
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": -5}):
            r = client.get("/projects", params=params, headers=h(member_key))
            assert_error(r, 422, "validation_error")

    def test_limit_100_ok(self, client, member_key):
        r = client.get("/projects", params={"limit": 100}, headers=h(member_key))
        assert r.status_code == 200

    def test_ordering_created_at_desc(self, client, member_key, make_project):
        import time

        a = make_project(name="older")
        time.sleep(1.1)  # second-precision timestamps: guarantee a distinct created_at
        b = make_project(name="newer")
        r = client.get("/projects", params={"limit": 100}, headers=h(member_key))
        ids = [p["id"] for p in r.json()["data"]]
        assert ids.index(b["id"]) < ids.index(a["id"])


class TestTaskFilters:
    def _seed(self, client, member_key, make_project):
        p = make_project()
        mk = lambda **kw: client.post(  # noqa: E731
            f"/projects/{p['id']}/tasks",
            json={"title": kw.pop("title", "t"), **kw},
            headers=h(member_key),
        )
        soon = iso(datetime.now(timezone.utc) + timedelta(days=1))
        later = iso(datetime.now(timezone.utc) + timedelta(days=30))
        assert mk(status="todo", priority=1, tags=["red"]).status_code == 201
        assert mk(status="in_progress", priority=5, tags=["blue"], due_date=soon).status_code == 201
        assert mk(status="todo", priority=5, tags=["red", "blue"], due_date=later).status_code == 201
        return p

    def test_filter_status(self, client, member_key, make_project):
        p = self._seed(client, member_key, make_project)
        r = client.get(f"/projects/{p['id']}/tasks", params={"status": "todo"}, headers=h(member_key))
        assert r.status_code == 200
        assert {t["status"] for t in r.json()["data"]} == {"todo"}
        assert len(r.json()["data"]) == 2

    def test_filter_priority(self, client, member_key, make_project):
        p = self._seed(client, member_key, make_project)
        r = client.get(f"/projects/{p['id']}/tasks", params={"priority": 5}, headers=h(member_key))
        assert len(r.json()["data"]) == 2

    def test_filter_tag(self, client, member_key, make_project):
        p = self._seed(client, member_key, make_project)
        r = client.get(f"/projects/{p['id']}/tasks", params={"tag": "red"}, headers=h(member_key))
        assert len(r.json()["data"]) == 2

    def test_filter_due_before(self, client, member_key, make_project):
        p = self._seed(client, member_key, make_project)
        cutoff = iso(datetime.now(timezone.utc) + timedelta(days=7))
        r = client.get(f"/projects/{p['id']}/tasks", params={"due_before": cutoff}, headers=h(member_key))
        assert len(r.json()["data"]) == 1

    def test_filters_combine(self, client, member_key, make_project):
        p = self._seed(client, member_key, make_project)
        r = client.get(
            f"/projects/{p['id']}/tasks",
            params={"status": "todo", "priority": 5, "tag": "blue"},
            headers=h(member_key),
        )
        assert len(r.json()["data"]) == 1

    def test_invalid_status_filter_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.get(f"/projects/{p['id']}/tasks", params={"status": "nope"}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_invalid_priority_filter_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.get(f"/projects/{p['id']}/tasks", params={"priority": "high"}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_invalid_due_before_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.get(f"/projects/{p['id']}/tasks", params={"due_before": "tomorrow"}, headers=h(member_key))
        assert_error(r, 422, "validation_error")
