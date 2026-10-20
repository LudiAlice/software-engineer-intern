from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.main import create_app

HEADER = "case_ref,applicant_name,id_number,dob,issue_date,image_ref\n"
ROW = "A,Alice,TEST-ID-1,2000-01-01,2020-01-01,scan.jpg\n"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as instance:
        yield instance


def upload(client, content=HEADER + ROW):
    return client.post("/api/batches", files={"file": ("input.csv", content, "text/csv")})


def case_id(client, batch):
    return client.get(f"/api/batches/{batch}/cases").json()["items"][0]["id"]


def set_status(client, ident, status):
    with connect(client.app.state.database_path, write=True) as db:
        db.execute("UPDATE cases SET status=? WHERE id=?", (status, ident))


def test_invalid_rows_partial_success(client):
    data = HEADER + ROW + ROW + "B,,TEST-ID-2,2000-02-30,2020-01-01,b.jpg\n"
    response = upload(client, data)
    assert response.status_code == 201
    result = response.json()
    assert (result["accepted"], result["rejected"]) == (1, 2)
    assert result["rejected_rows"][0]["row"] == 3
    assert "Duplicate" in result["rejected_rows"][0]["reasons"][0]
    assert len(result["rejected_rows"][1]["reasons"]) == 2
    assert result["counts"]["pending"] == 1


def test_sample_csv_counts(client):
    sample = Path(__file__).resolve().parents[2] / "data" / "account_applications.csv"
    result = upload(client, sample.read_bytes()).json()
    assert result["accepted"] + result["rejected"] == 50
    assert result["rejected"] > 0
    assert all(item["reasons"] for item in result["rejected_rows"])


@pytest.mark.parametrize("data", ["", "other\nvalue\n", HEADER + '"unterminated', '"broken header', b"\xff"])
def test_bad_document_is_422(client, data):
    assert upload(client, data).status_code == 422


def test_pagination_and_filter(client):
    batch = upload(client, HEADER + ROW + ROW.replace("A,Alice", "B,Bob")).json()["id"]
    first = client.get(f"/api/batches/{batch}/cases?page_size=1").json()
    second = client.get(f"/api/batches/{batch}/cases?page_size=1&page=2").json()
    assert first["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert client.get(f"/api/batches/{batch}/cases?status=ocr_done").json()["total"] == 0
    assert client.get(f"/api/batches/{batch}/cases?page=0").status_code == 422
    assert client.get(f"/api/batches/{batch}/cases?status=unknown").status_code == 422


def test_review_happy_path(client):
    ident = case_id(client, upload(client).json()["id"])
    # Q1 isolates staff review; Q2 integration tests exercise actual OCR.
    set_status(client, ident, "ocr_done")
    for stage, expected in [(1, "stage1_approved"), (2, "stage2_approved")]:
        response = client.post(f"/api/cases/{ident}/review", json={"stage": stage, "decision": "approve"})
        assert response.status_code == 200
        assert response.json()["status"] == expected


@pytest.mark.parametrize("status,stage", [("pending", 1), ("ocr_done", 2), ("ocr_failed", 1),
                                         ("stage1_approved", 1), ("stage1_rejected", 2),
                                         ("stage2_rejected", 2), ("exported", 2)])
def test_invalid_transition_returns_reason(client, status, stage):
    ident = case_id(client, upload(client).json()["id"])
    set_status(client, ident, status)
    response = client.post(f"/api/cases/{ident}/review", json={"stage": stage, "decision": "approve"})
    assert response.status_code == 409
    assert status in response.json()["detail"]


@pytest.mark.parametrize("stage,initial", [(1, "ocr_done"), (2, "stage1_approved")])
def test_rejection_terminal(client, stage, initial):
    ident = case_id(client, upload(client).json()["id"])
    set_status(client, ident, initial)
    response = client.post(f"/api/cases/{ident}/review", json={"stage": stage, "decision": "reject"})
    assert response.json()["status"] == f"stage{stage}_rejected"
    for next_stage in [1, 2]:
        assert client.post(f"/api/cases/{ident}/review", json={"stage": next_stage, "decision": "approve"}).status_code == 409


def test_concurrent_review_only_one_wins(client):
    ident = case_id(client, upload(client).json()["id"])
    set_status(client, ident, "ocr_done")
    def submit(_):
        return client.post(f"/api/cases/{ident}/review", json={"stage": 1, "decision": "approve"}).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(submit, range(2))) == [200, 409]


def test_missing_resources_and_readiness(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/ready").status_code == 200
    assert client.get("/api/batches/missing").status_code == 404
    assert client.get("/api/batches/missing/cases").status_code == 404
    assert client.post("/api/cases/missing/review", json={"stage": 1, "decision": "approve"}).status_code == 404

def test_review_rejects_invalid_stage(client):
    batch_id = upload(client).json()["id"]
    ident = case_id(client, batch_id)
    response = client.post(f"/api/cases/{ident}/review",json={"stage":3,"decision":"reject"})
    assert response.status_code == 422
    result = client.get(f"/api/batches/{batch_id}/cases")
    assert result.status_code == 200

    items = result.json()["items"]
    assert items[0]["id"] == ident
    assert items[0]["status"] == "pending"

def test_duplicate_review_keeps_status(client):
    batch_id = upload(client).json()["id"]
    ident = case_id(client,batch_id)
    set_status(client,ident,"ocr_done")
    response = client.post(f"/api/cases/{ident}/review",json={"stage":1,"decision":"approve"})
    assert response.status_code == 200
    response = client.post(f"/api/cases/{ident}/review",json={"stage":1,"decision":"approve"})
    assert response.status_code == 409
    result = client.get(f"/api/batches/{batch_id}/cases")
    assert result.status_code == 200

    items = result.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == ident
    assert items[0]["status"] == "stage1_approved"
