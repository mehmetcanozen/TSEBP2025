import httpx
import json

url = "http://localhost:8000/auth/register"
data = {
    "email": "debug_final@example.com",
    "username": "debug_final",
    "password": "Password123!"
}

try:
    with httpx.Client() as client:
        response = client.post(url, json=data)
        print(f"Status: {response.status_code}")
        try:
            print("Response JSON:")
            print(json.dumps(response.json(), indent=2))
        except:
            print("Raw Response Content:")
            print(response.text)
except Exception as e:
    print(f"Connection Error: {e}")
