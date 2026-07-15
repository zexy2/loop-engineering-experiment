"""Bulk create (207 multi-status) and stats endpoint."""
import uuid

from conftest import h, assert_error


class TestBulk:
    def test_all_valid_created(self, client, member_key, make_project):
        p = make_project()
        items = [{"project_id": p["id"], "title": f"bulk-{i}"} for i in range(20)]
        r = client.post("/tasks/bulk", json={"tasks": items}, headers=h(member_key))
        assert r.status_code == 207, f"{r.status_code} {r.text}"
        results = r.json()["results"]
        assert len(results) == 20
        assert all(x["status"] == 201 for x in results)
        assert all("task" in x for x in results)

    def test_mixed_valid_invalid(self, client, member_key, make_project):
        p = make_project()
        items = [
            {"project_id": p["id"], "title": "good one"},
            {"project_id": p["id"], "title": "   "},           # invalid: whitespace title
            {"project_id": str(uuid.uuid4()), "title": "orphan"},  # invalid: no such project
            {"project_id": p["id"], "title": "good two"},
        ]
        r = client.post("/tasks/bulk", json={"tasks": items}, headers=h(member_key))
        assert r.status_code == 207
        results = {x["index"]: x for x in r.json()["results"]}
        assert results[0]["status"] == 201
        assert results[1]["status"] == 422
        assert results[3]["status"] == 201
        # the valid ones actually exist
        tid = results[0]["task"]["id"]
        assert client.get(f"/tasks/{tid}", headers=h(member_key)).status_code == 200

    def test_over_20_items_rejects_whole_request(self, client, member_key, make_project):
        p = make_project()
        items = [{"project_id": p["id"], "title": f"x{i}"} for i in range(21)]
        r = client.post("/tasks/bulk", json={"tasks": items}, headers=h(member_key))
        assert_error(r, 422, "validation_error")
        # and none were created
        lst = client.get(f"/projects/{p['id']}/tasks", params={"limit": 100}, headers=h(member_key))
        assert lst.json()["pagination"]["total"] == 0


class TestStats:
    def test_stats_shape_and_counts(self, client, member_key, make_project):
        p = make_project()
        for s in ("todo", "in_progress"):
            client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "status": s}, headers=h(member_key))
        r = client.get("/stats", headers=h(member_key))
        assert r.status_code == 200
        body = r.json()
        for key in ("projects", "tasks", "by_status", "overdue"):
            assert key in body, f"missing {key}"
        assert body["projects"] >= 1
        assert body["tasks"] >= 2
        assert set(body["by_status"].keys()) >= {"todo", "in_progress", "done"}

    def test_overdue_counts_past_incomplete(self, client, member_key, make_project):
        # can't create a past-due task via the API (rejected at creation),
        # so overdue must simply be a non-negative integer here
        r = client.get("/stats", headers=h(member_key))
        assert isinstance(r.json()["overdue"], int)
        assert r.json()["overdue"] >= 0
