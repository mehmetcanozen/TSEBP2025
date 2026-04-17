from fastapi.testclient import TestClient
from main import app
import json
import traceback

client = TestClient(app)

def test_flow():
    test_user = {
        "email": "debug_user@example.com",
        "username": "debug_user",
        "password": "strongPassword123"
    }
    
    print("--- 1. KAYIT DENENİYOR ---")
    try:
        res = client.post("/auth/register", json=test_user)
        print(f"Status: {res.status_code}")
        print(f"Body: {res.text}")
    except Exception:
        traceback.print_exc()

    print("\n--- 2. GİRİŞ DENENİYOR ---")
    try:
        login_data = {
            "email": test_user["email"],
            "password": test_user["password"]
        }
        res = client.post("/auth/login", json=login_data)
        print(f"Status: {res.status_code}")
        print(f"Body: {res.text}")
    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    test_flow()
