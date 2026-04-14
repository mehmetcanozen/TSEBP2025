from fastapi.testclient import TestClient
from main import app
import traceback

client = TestClient(app)
print("Sending request...")
try:
    response = client.post('/auth/register', json={"username": "test7", "email": "test7@test.com", "password": "testpassword123"})
    print("STATUS:", response.status_code)
    print("BODY:", response.text)
except Exception as e:
    traceback.print_exc()
