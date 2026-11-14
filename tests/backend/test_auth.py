from tests.conftest import login


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_login_all_three_roles(client):
    for email, role in [("super@t.io", "super_admin"), ("centre@t.io", "centre_admin"), ("officer@t.io", "monitoring_officer")]:
        h = login(client, email)
        me = client.get("/api/auth/me", headers=h).json()
        assert me["role"] == role


def test_wrong_password_rejected(client):
    r = client.post("/api/auth/login", data={"username": "super@t.io", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_user_management_super_admin_only(client):
    body = {"email": "new@t.io", "full_name": "New", "password": "Passw0rd!", "role": "monitoring_officer"}
    assert client.post("/api/users", json=body, headers=login(client, "officer@t.io")).status_code == 403
    assert client.post("/api/users", json=body, headers=login(client, "centre@t.io")).status_code == 403
    assert client.get("/api/users").status_code == 401
    r = client.post("/api/users", json=body, headers=login(client, "super@t.io"))
    assert r.status_code == 201 and r.json()["email"] == "new@t.io"
    assert client.post("/api/users", json=body, headers=login(client, "super@t.io")).status_code == 409


def test_centre_admin_needs_centre_id(client):
    body = {"email": "ca@t.io", "full_name": "CA", "password": "Passw0rd!", "role": "centre_admin"}
    assert client.post("/api/users", json=body, headers=login(client, "super@t.io")).status_code == 422


def test_deactivated_user_cannot_login(client):
    h = login(client, "super@t.io")
    uid = next(u["id"] for u in client.get("/api/users", headers=h).json() if u["email"] == "officer@t.io")
    assert client.delete(f"/api/users/{uid}", headers=h).status_code == 204
    r = client.post("/api/auth/login", data={"username": "officer@t.io", "password": "Passw0rd!"})
    assert r.status_code == 401


def test_reserved_looking_domains_like_local_are_accepted(client):
    """Demo accounts use @skillwatch.local; strict email validators reject that domain."""
    h = login(client, "super@t.io")
    body = {"email": "Someone@Skillwatch.Local", "full_name": "Local User", "password": "Passw0rd!", "role": "monitoring_officer"}
    r = client.post("/api/users", json=body, headers=h)
    assert r.status_code == 201 and r.json()["email"] == "someone@skillwatch.local"
    assert login(client, "someone@skillwatch.local")


def test_malformed_email_is_rejected(client):
    h = login(client, "super@t.io")
    body = {"email": "not-an-email", "full_name": "X", "password": "Passw0rd!", "role": "monitoring_officer"}
    assert client.post("/api/users", json=body, headers=h).status_code == 422
