"""Project CRUD, validation, cascade delete, task_counts."""
import uuid

from conftest import h, assert_error


class TestProjectCreate:
    def test_create_returns_full_body(self, client, member_key):
        r = client.post("/projects", json={"name": "Alpha", "description": "d"}, headers=h(member_key))
        assert r.status_code == 201
        p = r.json()
        assert p["name"] == "Alpha"
        assert p["description"] == "d"
        uuid.UUID(p["id"])  # valid uuid
        assert p["created_at"].endswith("Z")
        assert p["task_counts"] == {"todo": 0, "in_progress": 0, "done": 0}
        client.delete(f"/projects/{p['id']}", headers=h(member_key))

    def test_name_is_trimmed(self, client, member_key):
        r = client.post("/projects", json={"name": "  My project  "}, headers=h(member_key))
        assert r.status_code == 201
        assert r.json()["name"] == "My project"
        client.delete(f"/projects/{r.json()['id']}", headers=h(member_key))

    def test_whitespace_only_name_is_422(self, client, member_key):
        assert_error(client.post("/projects", json={"name": "   "}, headers=h(member_key)), 422, "validation_error")

    def test_missing_name_is_422(self, client, member_key):
        assert_error(client.post("/projects", json={}, headers=h(member_key)), 422, "validation_error")

    def test_name_over_100_chars_is_422(self, client, member_key):
        assert_error(client.post("/projects", json={"name": "x" * 101}, headers=h(member_key)), 422, "validation_error")

    def test_description_over_500_chars_is_422(self, client, member_key):
        r = client.post("/projects", json={"name": "ok", "description": "x" * 501}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_unknown_field_is_422(self, client, member_key):
        r = client.post("/projects", json={"name": "ok", "color": "red"}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_malformed_json_is_422(self, client, member_key):
        r = client.post(
            "/projects",
            content=b'{"name": "broken"',
            headers={**h(member_key), "Content-Type": "application/json"},
        )
        assert_error(r, 422, "validation_error")


class TestProjectReadUpdateDelete:
    def test_get_by_id(self, client, member_key, make_project):
        p = make_project(name="Readable")
        r = client.get(f"/projects/{p['id']}", headers=h(member_key))
        assert r.status_code == 200
        assert r.json()["name"] == "Readable"

    def test_get_missing_is_404(self, client, member_key):
        r = client.get(f"/projects/{uuid.uuid4()}", headers=h(member_key))
        assert_error(r, 404, "not_found")

    def test_malformed_uuid_is_404(self, client, member_key):
        r = client.get("/projects/not-a-uuid", headers=h(member_key))
        assert_error(r, 404, "not_found")

    def test_patch_name(self, client, member_key, make_project):
        p = make_project()
        r = client.patch(f"/projects/{p['id']}", json={"name": "Renamed"}, headers=h(member_key))
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_patch_empty_body_is_422(self, client, member_key, make_project):
        p = make_project()
        assert_error(client.patch(f"/projects/{p['id']}", json={}, headers=h(member_key)), 422, "validation_error")

    def test_patch_unknown_field_is_422(self, client, member_key, make_project):
        p = make_project()
        r = client.patch(f"/projects/{p['id']}", json={"owner": "me"}, headers=h(member_key))
        assert_error(r, 422, "validation_error")

    def test_delete_is_204_then_404(self, client, member_key, make_project):
        p = make_project()
        r = client.delete(f"/projects/{p['id']}", headers=h(member_key))
        assert r.status_code == 204
        assert_error(client.get(f"/projects/{p['id']}", headers=h(member_key)), 404, "not_found")

    def test_delete_cascades_to_tasks(self, client, member_key, make_project):
        p = make_project()
        t = client.post(f"/projects/{p['id']}/tasks", json={"title": "doomed"}, headers=h(member_key))
        assert t.status_code == 201
        tid = t.json()["id"]
        assert client.delete(f"/projects/{p['id']}", headers=h(member_key)).status_code == 204
        assert_error(client.get(f"/tasks/{tid}", headers=h(member_key)), 404, "not_found")


class TestTaskCounts:
    def test_counts_reflect_statuses(self, client, member_key, make_project):
        p = make_project()
        for status in ("todo", "todo", "in_progress"):
            r = client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "status": status}, headers=h(member_key))
            assert r.status_code == 201
        done = client.post(f"/projects/{p['id']}/tasks", json={"title": "t", "status": "in_progress"}, headers=h(member_key)).json()
        rc = client.post(f"/tasks/{done['id']}/complete", headers=h(member_key))
        assert rc.status_code == 200
        r = client.get(f"/projects/{p['id']}", headers=h(member_key))
        assert r.json()["task_counts"] == {"todo": 2, "in_progress": 1, "done": 1}
