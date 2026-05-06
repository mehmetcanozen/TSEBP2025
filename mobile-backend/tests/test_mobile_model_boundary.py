def test_model_routes_are_not_registered(client, auth_headers):
    response = client.get("/model/latest?platform=android", headers=auth_headers)
    assert response.status_code == 404

    response = client.get("/model/download/1?platform=android", headers=auth_headers)
    assert response.status_code == 404

    response = client.get("/model/versions", headers=auth_headers)
    assert response.status_code == 404


def test_server_side_separation_routes_are_not_registered(client, auth_headers):
    response = client.post("/separation/ping", headers=auth_headers)
    assert response.status_code == 404

    response = client.post("/separation/separate", headers=auth_headers)
    assert response.status_code == 404


def test_openapi_has_no_model_or_separation_paths(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    assert not any(path.startswith("/model") for path in paths)
    assert not any(path.startswith("/separation") for path in paths)
