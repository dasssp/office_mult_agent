from fastapi.testclient import TestClient

from app.main import app


def test_upload_csv_and_reject_formula_injection() -> None:
    client = TestClient(app)
    valid = client.post("/files/upload", files={"file": ("data.csv", "name,value\na,1\n", "text/csv")})
    assert valid.status_code == 200
    unsafe = client.post("/files/upload", files={"file": ("bad.csv", "name,value\na,=1+1\n", "text/csv")})
    assert unsafe.status_code == 422


def test_analyze_uploaded_file() -> None:
    client = TestClient(app)
    uploaded = client.post("/files/upload", files={"file": ("data.json", '[{"amount": 1}, {"amount": null}]', "application/json")})
    result = client.post(f"/analysis/files/{uploaded.json()['file_id']}")
    assert result.json()["null_counts"] == {"amount": 1}
