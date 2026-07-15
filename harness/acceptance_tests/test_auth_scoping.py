"""Health, auth, and multi-tenancy scoping."""
import uuid

from conftest import h, assert_error


class TestHealth:
    def test_health_ok_without_auth(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestAuth:
    def test_missing_key_is_401(self, client):
        assert_error(client.get("/projects"), 401, "unauthorized")

    def test_unknown_key_is_401(self, client):
        r = client.get("/projects", headers=h("definitely-not-a-real-key"))
        assert_error(r, 401, "unauthorized")

    def test_valid_key_is_accepted(self, client, member_key):
        r = client.get("/projects", headers=h(member_key))
        assert r.status_code == 200

    def test_admin_endpoint_forbidden_for_member(self, client, member_key):
        assert_error(client.get("/admin/keys", headers=h(member_key)), 403, "forbidden")

    def test_admin_endpoint_ok_for_admin(self, client, admin_key):
        r = client.get("/admin/keys", headers=h(admin_key))
        assert r.status_code == 200

    def test_admin_keys_never_leak_key_material(self, client, admin_key, member_key):
        r = client.get("/admin/keys", headers=h(admin_key))
        assert r.status_code == 200
        text = r.text
        assert admin_key not in text
        assert member_key not in text


class TestScoping:
    def test_other_keys_project_is_404_not_403(self, client, admin_key, make_project):
        p = make_project()  # owned by member
        r = client.get(f"/projects/{p['id']}", headers=h(admin_key))
        assert_error(r, 404, "not_found")

    def test_list_does_not_include_other_keys_projects(self, client, admin_key, make_project):
        p = make_project()
        r = client.get("/projects", params={"limit": 100}, headers=h(admin_key))
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["data"]]
        assert p["id"] not in ids

    def test_cannot_delete_other_keys_project(self, client, admin_key, member_key, make_project):
        p = make_project()
        r = client.delete(f"/projects/{p['id']}", headers=h(admin_key))
        assert_error(r, 404, "not_found")
        # still there for its owner
        r2 = client.get(f"/projects/{p['id']}", headers=h(member_key))
        assert r2.status_code == 200

    def test_cannot_create_task_in_other_keys_project(self, client, admin_key, make_project):
        p = make_project()
        r = client.post(f"/projects/{p['id']}/tasks", json={"title": "sneaky"}, headers=h(admin_key))
        assert_error(r, 404, "not_found")
