"""Reproducible Q2 process-kill recovery and lost-receipt evidence.

Uses only supplied fictional data and mocks. Isolated temporary database/ports;
never reads local configuration files or changes an existing running service.
"""
from collections import Counter
import argparse
import hashlib
import json
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "q1_api"))


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait(predicate, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError("Timed out waiting for test condition")


def run(output_path=None, temp_root=None):
    children = []
    with tempfile.TemporaryDirectory(prefix="gekko-validation-", dir=temp_root) as temp:
        directory = Path(temp)
        ocr_port, onboard_port, api_port = free_port(), free_port(), free_port()
        base, ocr_base, onboard_base = [f"http://127.0.0.1:{p}" for p in (api_port, ocr_port, onboard_port)]
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "q1_api"), OCR_URL=ocr_base + "/ocr/parse",
                   ONBOARDING_URL=onboard_base + "/ingest", HTTP_TIMEOUT="0.15",
                   RETRY_ATTEMPTS="8", RETRY_BACKOFF="0.01", OCR_HANG_SECONDS="0.6",
                   OCR_FAIL_RATE="0.2", OCR_HANG_RATE="0.1", OCR_SEED="42",
                   ONBOARDING_FAIL_RATE="0", ONBOARDING_LOST_RATE="1", ONBOARDING_LOST_SECONDS="0.6")
        client = httpx.Client(timeout=3, trust_env=False)

        def call(method, url, **kwargs):
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

        def start(command, health, extra=None):
            process = subprocess.Popen([sys.executable, *command], cwd=ROOT, env={**env, **(extra or {})},
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            children.append(process)
            def ready():
                if process.poll() is not None:
                    raise AssertionError("Validation child exited during startup")
                try:
                    return call("GET", health)
                except httpx.HTTPError:
                    return False
            wait(ready, 15)
            return process

        def start_api(database):
            return start(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
                         base + "/api/ready", {"DATABASE_PATH": str(database)})

        def stop(process):
            process.kill()  # Only the exact child created by this validation harness.
            process.wait(timeout=10)

        def import_batch():
            with (ROOT / "data" / "account_applications.csv").open("rb") as data:
                return call("POST", base + "/api/batches", files={"file": ("sample.csv", data, "text/csv")})

        def process(batch_id):
            return call("POST", base + f"/api/batches/{batch_id}/process?retry_failed=true")

        def finished(batch_id):
            def check():
                result = call("GET", base + f"/api/batches/{batch_id}")
                return result if not result["processing"] and result["counts"]["pending"] == 0 else False
            return wait(check)

        def snapshot(batch_id):
            cases = call("GET", base + f"/api/batches/{batch_id}/cases?page_size=100")["items"]
            return {case["case_ref"]: {"status": case["status"], "parsed_fields": case["parsed_fields"]} for case in cases}

        try:
            ocr = start(["mock_ocr/server.py", "--port", str(ocr_port)], ocr_base + "/online")
            start(["mock_onboarding/server.py", "--port", str(onboard_port)], onboard_base + "/online")
            api = start_api(directory / "clean.db")
            clean = import_batch()
            started = time.monotonic()
            process(clean["id"])
            response_seconds = time.monotonic() - started
            clean_finished = finished(clean["id"])
            clean_state = snapshot(clean["id"])
            clean_requests = call("GET", ocr_base + "/debug/requests")
            stop(api)
            stop(ocr)

            # Reset the mock RNG by restarting this test's own mock process.
            ocr = start(["mock_ocr/server.py", "--port", str(ocr_port)], ocr_base + "/online")
            database = directory / "recovery.db"
            api = start_api(database)
            interrupted = import_batch()
            process(interrupted["id"])
            wait(lambda: len(call("GET", ocr_base + "/debug/requests")) >= 3)
            before_kill = call("GET", base + f'/api/batches/{interrupted["id"]}')
            assert before_kill["counts"]["pending"] > 0
            stop(api)
            api = start_api(database)
            process(interrupted["id"])
            recovered = finished(interrupted["id"])
            recovered_state = snapshot(interrupted["id"])
            assert recovered_state == clean_state, "Recovered status/fields differ from clean processing"
            recovered_requests = call("GET", ocr_base + "/debug/requests")

            cases = call("GET", base + f'/api/batches/{interrupted["id"]}/cases?status=ocr_done&page_size=100')["items"]
            for case in cases:
                for stage in [1, 2]:
                    call("POST", base + f'/api/cases/{case["id"]}/review', json={"stage": stage, "decision": "approve"})
            export = call("POST", base + f'/api/batches/{interrupted["id"]}/export')["export"]
            export_url = base + f'/api/exports/{export["id"]}'
            receipt = wait(lambda: (item if (item := call("GET", export_url))["status"] == "delivered" else False))
            deliveries = call("GET", onboard_base + "/debug/deliveries")
            assert len(deliveries) == 1 and deliveries[0]["attempts"] >= 2
            assert deliveries[0]["idempotency_key"] == export["id"]
            assert call("POST", base + f'/api/batches/{interrupted["id"]}/export')["export"] is None

            counts = Counter(item["outcome"] for item in clean_requests)
            report = {
                "configuration": {"ocr_fail_rate": .2, "ocr_hang_rate": .1, "ocr_seed": 42,
                                  "mock_delay_seconds": .6, "client_timeout_seconds": .15,
                                  "attempt_limit": 8, "backoff_seconds": .01,
                                  "onboarding_fail_rate": 0, "onboarding_lost_rate": 1},
                "import": {"accepted": clean["accepted"], "rejected": clean["rejected"], "rejected_rows": clean["rejected_rows"]},
                "process_response_seconds": round(response_seconds, 4),
                "clean_counts": clean_finished["counts"], "counts_before_process_kill": before_kill["counts"],
                "recovered_counts": recovered["counts"], "clean_equals_recovered": recovered_state == clean_state,
                "ocr_attempt_outcomes": dict(counts),
                "ocr_attempt_rates": {k: round(v / len(clean_requests), 6) for k, v in counts.items()},
                "clean_ocr_requests": clean_requests, "recovery_ocr_requests": recovered_requests,
                "clean_final_state": clean_state, "recovered_final_state": recovered_state,
                "export": receipt, "deliveries": deliveries,
            }
            sources = [*sorted((ROOT / "q1_api" / "app").glob("*.py")),
                       ROOT / "mock_ocr" / "server.py", ROOT / "mock_onboarding" / "server.py",
                       ROOT / "data" / "account_applications.csv", Path(__file__).resolve()]
            report["provenance"] = {
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "python_version": sys.version.split()[0],
                "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                "note": "Executed against the Q2 submission source with independent HTTP services; accelerated fault-injection settings, not default deployment settings.",
            }
            destination = Path(output_path) if output_path else ROOT / "q2_integration" / "evidence" / "live-validation.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"accepted": clean["accepted"], "rejected": clean["rejected"],
                              "clean_equals_recovered": True, "ocr_attempt_outcomes": dict(counts),
                              "single_ingestion_attempts": deliveries[0]["attempts"], "report": str(destination)}, indent=2))
        finally:
            client.close()
            for process in children:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Evidence JSON destination")
    parser.add_argument("--temp-root", help="Existing directory for isolated temporary databases")
    args = parser.parse_args()
    run(args.output, args.temp_root)
