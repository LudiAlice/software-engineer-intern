import csv
import hashlib
import io
import json
import threading
import time

import httpx
from fastapi.testclient import TestClient

from app.integrations import Settings
from app.main import create_app
from test_app import HEADER, ROW, upload, case_id, set_status, client

PARSED = {"id_number": "TEST-ID-123", "full_name": "OCR Name", "dob": "1990-01-01",
          "issue_date": "2020-01-01", "confidence": .95}


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("Background job did not finish")


def done(client, batch):
    return not client.get(f"/api/batches/{batch}").json()["processing"]


def test_lifecycle_with_retries_lost_receipt_and_repeated_export(tmp_path):
    attempts, ingestions = [], {}
    def service(request):
        if request.url.path == "/ocr/parse":
            attempts.append(json.loads(request.content))
            if len(attempts) == 1:
                return httpx.Response(500, json={"error": "temporary"})
            return httpx.Response(200, json=PARSED)
        key = request.headers["Idempotency-Key"]
        if key not in ingestions:
            ingestions[key] = {"delivery_id": "D1", "idempotency_key": key,
                               "file_name": request.headers["X-File-Name"],
                               "sha256": hashlib.sha256(request.content).hexdigest(), "attempts": 1}
            raise httpx.ReadTimeout("Simulated lost receipt")
        ingestions[key]["attempts"] += 1
        return httpx.Response(200, json=ingestions[key])
    app = create_app(tmp_path / "app.db", settings=Settings(backoff=0), transport=httpx.MockTransport(service))
    with TestClient(app) as client:
        batch = upload(client).json()["id"]
        assert client.post(f"/api/batches/{batch}/process").status_code == 202
        wait_until(lambda: done(client, batch))
        ident = case_id(client, batch)
        for stage in [1, 2]:
            assert client.post(f"/api/cases/{ident}/review", json={"stage": stage, "decision": "approve"}).status_code == 200
        export = client.post(f"/api/batches/{batch}/export").json()["export"]
        url = f'/api/exports/{export["id"]}'
        wait_until(lambda: client.get(url).json()["status"] == "delivered")
        result = client.get(url).json()
        assert len(ingestions) == 1
        assert result["delivery_attempts"] == 2
        assert result["receipt"]["attempts"] == 2
        assert client.post(f"/api/batches/{batch}/export").json()["export"] is None
        assert client.post(url + "/deliver").json()["scheduled"] is False
        records = list(csv.DictReader(io.StringIO(client.get(url + "/download").text)))
        assert len(records) == 1 and records[0]["applicant_name"] == "OCR Name"
        assert client.get(f"/api/batches/{batch}").json()["counts"]["exported"] == 1


def test_ocr_422_is_not_retried_and_exhaustion_can_be_retried(tmp_path):
    mode, calls = ["unreadable"], []
    def service(request):
        calls.append(1)
        if mode[0] == "unreadable":
            return httpx.Response(422, json={"error": "bad scan"})
        if mode[0] == "down":
            return httpx.Response(500, json={"error": "temporarily down"})
        return httpx.Response(200, json=PARSED)
    app = create_app(tmp_path / "app.db", settings=Settings(attempts=3, backoff=0), transport=httpx.MockTransport(service))
    with TestClient(app) as client:
        first = upload(client).json()["id"]
        client.post(f"/api/batches/{first}/process")
        wait_until(lambda: done(client, first))
        assert len(calls) == 1
        assert client.get(f"/api/batches/{first}/cases").json()["items"][0]["failure_reason"] == "HTTP 422: bad scan"
        client.post(f"/api/batches/{first}/process?retry_failed=true")
        wait_until(lambda: done(client, first))
        assert len(calls) == 1
        mode[0] = "down"
        second = upload(client).json()["id"]
        client.post(f"/api/batches/{second}/process")
        wait_until(lambda: done(client, second))
        assert len(calls) == 4
        failed = client.get(f"/api/batches/{second}/cases").json()["items"][0]
        assert failed["status"] == "ocr_failed" and failed["retryable"] is True
        mode[0] = "ok"
        client.post(f"/api/batches/{second}/process?retry_failed=true")
        wait_until(lambda: done(client, second))
        assert client.get(f"/api/batches/{second}").json()["counts"]["ocr_done"] == 1
        assert len(calls) == 5


def test_process_returns_before_ocr_and_duplicate_trigger_is_coalesced(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def service(request):
        entered.set()
        assert release.wait(3)
        return httpx.Response(200, json=PARSED)
    app = create_app(tmp_path / "app.db", transport=httpx.MockTransport(service))
    with TestClient(app) as client:
        batch = upload(client).json()["id"]
        try:
            assert client.post(f"/api/batches/{batch}/process").status_code == 202
            assert entered.wait(1)
            assert client.post(f"/api/batches/{batch}/process").json()["scheduled"] is False
            assert client.get(f"/api/batches/{batch}").json()["counts"]["pending"] == 1
        finally:
            release.set()
        wait_until(lambda: done(client, batch))


def test_export_restart_reuses_identical_bytes_and_key(tmp_path):
    path, sent = tmp_path / "app.db", []
    def unavailable(request):
        sent.append((request.headers["Idempotency-Key"], request.content))
        raise httpx.ConnectError("Unavailable")
    with TestClient(create_app(path, settings=Settings(attempts=1), transport=httpx.MockTransport(unavailable))) as client:
        batch = upload(client).json()["id"]
        set_status(client, case_id(client, batch), "stage2_approved")
        ident = client.post(f"/api/batches/{batch}/export").json()["export"]["id"]
        wait_until(lambda: client.get(f"/api/exports/{ident}").json()["status"] == "failed")
    def recovered(request):
        sent.append((request.headers["Idempotency-Key"], request.content))
        return httpx.Response(200, json={"delivery_id": "D1", "idempotency_key": ident,
                              "file_name": request.headers["X-File-Name"], "sha256": hashlib.sha256(request.content).hexdigest()})
    with TestClient(create_app(path, transport=httpx.MockTransport(recovered))) as client:
        client.post(f"/api/exports/{ident}/deliver")
        wait_until(lambda: client.get(f"/api/exports/{ident}").json()["status"] == "delivered")
        assert sent[0] == sent[1]


def test_export_excludes_rejections_and_uses_new_key_for_later_approvals(client):
    from app.exports import create_export, export_summary
    batch = upload(client, HEADER + ROW + ROW.replace("A,Alice", "B,Bob") + ROW.replace("A,Alice", "C,Cara")).json()["id"]
    ids = [row["id"] for row in client.get(f"/api/batches/{batch}/cases").json()["items"]]
    for ident, status in zip(ids, ["stage2_approved", "stage2_rejected", "stage1_approved"]):
        set_status(client, ident, status)
    path = client.app.state.database_path
    first = create_export(path, batch)
    assert export_summary(path, first)["case_count"] == 1
    assert create_export(path, batch) is None
    set_status(client, ids[2], "stage2_approved")
    second = create_export(path, batch)
    assert second != first and export_summary(path, second)["case_count"] == 1


def test_pending_cases_resume_after_restart(tmp_path):
    path = tmp_path / "app.db"
    with TestClient(create_app(path)) as client:
        batch = upload(client).json()["id"]
    with TestClient(create_app(path, transport=httpx.MockTransport(lambda req: httpx.Response(200, json=PARSED)))) as client:
        client.post(f"/api/batches/{batch}/process")
        wait_until(lambda: done(client, batch))
        assert client.get(f"/api/batches/{batch}").json()["counts"]["ocr_done"] == 1


def test_mismatched_receipt_is_not_success(tmp_path):
    with TestClient(create_app(tmp_path / "db", transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"delivery_id": "wrong"})))) as client:
        batch = upload(client).json()["id"]
        set_status(client, case_id(client, batch), "stage2_approved")
        ident = client.post(f"/api/batches/{batch}/export").json()["export"]["id"]
        wait_until(lambda: client.get(f"/api/exports/{ident}").json()["status"] == "failed")
        assert client.get(f"/api/exports/{ident}").json()["receipt"] is None
