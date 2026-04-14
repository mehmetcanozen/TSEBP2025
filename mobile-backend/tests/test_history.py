"""
History endpoint testleri.
"""

def test_save_history(client, auth_headers):
    res = client.post("/history", json={
        "file_name": "vocals.wav",
        "duration_seconds": 120.5,
        "model_version": "1.0.0",
        "platform": "android",
        "status": "success",
    }, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["file_name"] == "vocals.wav"

def test_get_history_paginated(client, auth_headers):
    for i in range(5):
        client.post("/history", json={"file_name": f"file{i}.wav", "status": "success"}, headers=auth_headers)
    res = client.get("/history?page=1&per_page=3", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    assert len(data["items"]) == 3
    assert data["page"] == 1

def test_history_second_page(client, auth_headers):
    for i in range(5):
        client.post("/history", json={"file_name": f"file{i}.wav", "status": "success"}, headers=auth_headers)
    res = client.get("/history?page=2&per_page=3", headers=auth_headers)
    data = res.json()
    assert len(data["items"]) == 2

def test_clear_history(client, auth_headers):
    client.post("/history", json={"file_name": "a.wav", "status": "success"}, headers=auth_headers)
    res = client.delete("/history", headers=auth_headers)
    assert res.status_code == 200
    res2 = client.get("/history", headers=auth_headers)
    assert res2.json()["total"] == 0

def test_history_requires_auth(client):
    res = client.get("/history")
    assert res.status_code in (401, 403)

def test_users_see_only_own_history(client):
    # İki farklı kullanıcı
    u1 = {"email": "u1@test.com", "username": "user1", "password": "pass12345"}
    u2 = {"email": "u2@test.com", "username": "user2", "password": "pass12345"}

    client.post("/auth/register", json=u1)
    client.post("/auth/register", json=u2)

    def login(u):
        r = client.post("/auth/login", json={"email": u["email"], "password": u["password"]})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    h1, h2 = login(u1), login(u2)

    client.post("/history", json={"file_name": "u1_file.wav", "status": "success"}, headers=h1)
    client.post("/history", json={"file_name": "u1_file2.wav", "status": "success"}, headers=h1)
    client.post("/history", json={"file_name": "u2_file.wav", "status": "success"}, headers=h2)

    r1 = client.get("/history", headers=h1).json()
    r2 = client.get("/history", headers=h2).json()

    assert r1["total"] == 2
    assert r2["total"] == 1
