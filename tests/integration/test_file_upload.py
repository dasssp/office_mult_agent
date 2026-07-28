from fastapi.testclient import TestClient

from app.main import app


def test_upload_csv_and_reject_formula_injection() -> None:
    client = TestClient(app)
    valid = client.post("/files/upload", files={"file": ("data.csv", "name,value\na,1\n", "text/csv")})
    assert valid.status_code == 200
    unsafe = client.post("/files/upload", files={"file": ("bad.csv", "name,value\na,=1+1\n", "text/csv")})
    assert unsafe.status_code == 422
