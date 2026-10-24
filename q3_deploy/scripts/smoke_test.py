"""HTTP end-to-end driver usable both inside Compose and on the host."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import httpx


def smoke(base, sample):
    with httpx.Client(base_url=base, timeout=10, trust_env=False) as client:
        def call(method, url, **kwargs):
            result = client.request(method, url, **kwargs)
            result.raise_for_status()
            return result.json()

        def wait_for(url, predicate, timeout=300):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                result = call("GET", url)
                if predicate(result):
                    return result
                time.sleep(.1)
            raise AssertionError(f"Timed out waiting for {url}")

        assert call("GET", "/api/ready")["ready"]
        with sample.open("rb") as data:
            batch = call("POST", "/api/batches", files={"file": (sample.name, data, "text/csv")})
        assert batch["accepted"] > 0 and batch["accepted"] + batch["rejected"] == 50
        ident = batch["id"]
        call("POST", f"/api/batches/{ident}/process")
        finished = wait_for(f"/api/batches/{ident}", lambda b: not b["processing"] and b["counts"]["pending"] == 0)
        cases = call("GET", f"/api/batches/{ident}/cases?status=ocr_done&page_size=100")["items"]
        assert cases, "No successfully parsed cases"
        for case in cases:
            for stage in (1, 2):
                call("POST", f'/api/cases/{case["id"]}/review', json={"stage": stage, "decision": "approve"})
        export = call("POST", f"/api/batches/{ident}/export")["export"]
        export_url = f'/api/exports/{export["id"]}'
        delivery = wait_for(export_url, lambda e: e["status"] in ("delivered", "failed"))
        assert delivery["status"] == "delivered", delivery["failure_reason"]
        data = client.get(export_url + "/download")
        data.raise_for_status()
        assert hashlib.sha256(data.content).hexdigest() == delivery["receipt"]["sha256"]
        assert export["case_count"] == len(cases)
        assert call("POST", f"/api/batches/{ident}/export")["export"] is None
        return {"batch_id": ident, "accepted": batch["accepted"], "rejected": batch["rejected"],
                "ocr_counts": finished["counts"], "export": delivery,
                "final_counts": call("GET", f"/api/batches/{ident}")["counts"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--sample", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "account_applications.csv")
    args = parser.parse_args()
    print(json.dumps(smoke(args.base, args.sample), indent=2))
