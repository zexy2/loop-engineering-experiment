"""Task CRUD, validation, status transitions, tags, complete action."""
import uuid
from datetime import datetime, timedelta, timezone

from conftest import h, assert_error


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def future(days=7):
    return iso(datetime.now(timezone.utc) + timedelta(days=days))


def past(days=7):
    return iso(datetime.now(timezone.utc) - timedelta(days=days))


class TestTaskCreate:
    def test_defaults(self, client, member_key, make_project):
        p = make_project()
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "Basic"}, headers=h(member_key))
        assert r.status_code == 201
        t = r.json()
        assert t["status"] == "todo"
        assert t["priority"] == 3
        assert t["project_id"] == p["id"]
        assert t["created_at"].endswith("Z")
        assert t["updated_at"].endswith("Z")

    def test_title_trimmed(self, client, member_key, make_task):
        t = make_task(title="  Trim me  ")
        assert t["title"] == "Trim me"

    def test_whitespace_title_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "   "}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_title_over_200_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "x" * 201}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_priority_bounds(self, client, member_key, make_project):
        p = make_project()
        for bad in (0, 6, -1):
            r = client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "priority": bad}, headers=h(member_key))
            assert_error(r, 422, "validation_error")
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "priority": 5}, headers=h(member_key))
        assert r.status_code == 201

    def test_invalid_status_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "status": "blocked"}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_past_due_date_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "due_date": past()}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_future_due_date_ok(self, client, member_key, make_task):
        t = make_task(due_date=future())
        assert t["due_date"] is not None

    def test_create_in_missing_project_is_404(self, client, member_key):
        r = client.post(f"/projects/{uuid.uuid4()}/tasks", json={"title": "t"}, headers=h(member_key))
        assert_error(r, 404, "not_found")


class TestTags:
    def test_tags_lowercased(self, client, member_key, make_task):
        t = make_task(tags=["URGENT", "Home"])
        assert sorted(t["tags"]) == ["home", "urgent"]

    def test_duplicate_after_lowercasing_is_409(self, client, member_key, make_project):
        p = make_project()
        r = client.post(
            f"/projects/{p['id']}/tasks",
            json={"title": "t", "tags": ["URGENT", "urgent"]},
            headers=h(member_key),
        )
        assert_error(r, 409, "conflict")

    def test_more_than_10_tags_is_422(self, client, member_key, make_project):
        p = make_project()
        tags = [f"tag{i}" for i in range(11)]
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "tags": tags}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_tag_over_30_chars_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "tags": ["x" * 31]}, headers=h(member_key))
        assert_error(r, 422, "validation_error")


class TestTaskUpdate:
    def test_patch_updates_updated_at(self, client, member_key, make_task):
        t = make_task()
        r = client.patch(f"/tasks/{t['id']}", json={"title": "New title"}, headers=h(member_key))
        assert r.status_code == 200
        assert r.json()["title"] == "New title"
        assert r.json()["updated_at"] >= t["updated_at"]

    def test_move_between_owned_projects(self, client, member_key, make_project, make_task):
        p2 = make_project()
        t = make_task()
        r = client.patch(f"/tasks/{t['id']}", json={"project_id": p2["id"]}, headers=h(member_key))
        assert r.status_code == 200
        assert r.json()["project_id"] == p2["id"]

    def test_empty_patch_is_422(self, client, member_key, make_task):
        t = make_task()
        assert_error(client.patch(f"/tasks/{t['id']}", json={}, headers=h(member_key)), 422, "validation_error")

    def test_done_to_todo_is_422(self, client, member_key, make_task):
        t = make_task()
        assert client.post(f"/tasks/{t['id']}/complete", headers=h(member_key)).status_code == 200
        r = client.patch(f"/tasks/{t['id']}", json={"status": "todo"}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_done_to_in_progress_is_allowed(self, client, member_key, make_task):
        t = make_task()
        assert client.post(f"/tasks/{t['id']}/complete", headers=h(member_key)).status_code == 200
        r = client.patch(f"/tasks/{t['id']}", json={"status": "in_progress"}, headers=h(member_key))
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"


class TestComplete:
    def test_complete_sets_done(self, client, member_key, make_task):
        t = make_task()
        r = client.post(f"/tasks/{t['id']}/complete", headers=h(member_key))
        assert r.status_code == 200
        assert r.json()["status"] == "done"

    def test_completing_done_task_is_422_and_mentions_it(self, client, member_key, make_task):
        t = make_task()
        client.post(f"/tasks/{t['id']}/complete", headers=h(member_key))
        r = client.post(f"/tasks/{t['id']}/complete", headers=h(member_key))
        assert_error(r, 422, "validation_error")
        assert "done" in r.json()["error"]["message"].lower()


class TestTaskDelete:
    def test_delete_204_then_404(self, client, member_key, make_task):
        t = make_task()
        assert client.delete(f"/tasks/{t['id']}", headers=h(member_key)).status_code == 204
        assert_error(client.get(f"/tasks/{t['id']}", headers=h(member_key)), 404, "not_found")
