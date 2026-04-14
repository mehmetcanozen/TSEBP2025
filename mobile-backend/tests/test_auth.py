"""
Auth endpoint testleri.
Fixtures: client, registered_user, auth_headers, auth_tokens (conftest.py'den)
"""

VALID_USER = {
    "email": "test@example.com",
    "username": "testuser2",
    "password": "strongpass123",
}

def test_register_success(client):
    res = client.post("/auth/register", json=VALID_USER)
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == VALID_USER["email"]
    assert data["username"] == VALID_USER["username"]
    assert "password" not in data

def test_register_duplicate_email(client):
    client.post("/auth/register", json=VALID_USER)
    res = client.post("/auth/register", json=VALID_USER)
    assert res.status_code == 400
    assert "e-posta" in res.json()["detail"].lower()

def test_register_duplicate_username(client):
    client.post("/auth/register", json=VALID_USER)
    res = client.post("/auth/register", json={**VALID_USER, "email": "other@example.com"})
    assert res.status_code == 400

def test_register_short_password(client):
    res = client.post("/auth/register", json={**VALID_USER, "password": "123"})
    assert res.status_code == 422

def test_login_success(client, registered_user):
    res = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

def test_login_wrong_password(client, registered_user):
    res = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": "yanlis_sifre",
    })
    assert res.status_code == 401

def test_login_nonexistent_user(client):
    res = client.post("/auth/login", json={"email": "yok@example.com", "password": "sifre123"})
    assert res.status_code == 401

def test_me_with_valid_token(client, auth_headers, registered_user):
    res = client.get("/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["email"] == registered_user["email"]

def test_me_without_token(client):
    res = client.get("/auth/me")
    assert res.status_code in (401, 403)

def test_me_with_invalid_token(client):
    res = client.get("/auth/me", headers={"Authorization": "Bearer gecersiz.token.xyz"})
    assert res.status_code in (401, 403)

def test_refresh_token(client, auth_tokens):
    res = client.post("/auth/refresh", json={"refresh_token": auth_tokens["refresh_token"]})
    assert res.status_code == 200
    assert "access_token" in res.json()
    # Token rotation: eski token artık geçersiz
    res2 = client.post("/auth/refresh", json={"refresh_token": auth_tokens["refresh_token"]})
    assert res2.status_code == 401

def test_logout(client, auth_tokens):
    res = client.post("/auth/logout", json={"refresh_token": auth_tokens["refresh_token"]})
    assert res.status_code == 200
    res2 = client.post("/auth/refresh", json={"refresh_token": auth_tokens["refresh_token"]})
    assert res2.status_code == 401

def test_change_password(client, auth_headers, registered_user):
    res = client.put("/auth/change-password", json={
        "old_password": registered_user["password"],
        "new_password": "yeni_guclu_sifre_123",
    }, headers=auth_headers)
    assert res.status_code == 200
    res2 = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    assert res2.status_code == 401

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
