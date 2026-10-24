"""Bounded retries and recoverable jobs, without a second application service."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import logging
import os
import threading

import httpx

from .db import connect

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    ocr_url: str = "http://127.0.0.1:9100/ocr/parse"
    onboarding_url: str = "http://127.0.0.1:9200/ingest"
    timeout: float = 2.0
    attempts: int = 5
    backoff: float = 0.2

    @classmethod
    def from_environment(cls):
        result = cls(os.getenv("OCR_URL", cls.ocr_url), os.getenv("ONBOARDING_URL", cls.onboarding_url),
                     float(os.getenv("HTTP_TIMEOUT", "2")), int(os.getenv("RETRY_ATTEMPTS", "5")),
                     float(os.getenv("RETRY_BACKOFF", "0.2")))
        if not (0 < result.timeout <= 60 and 1 <= result.attempts <= 10 and 0 <= result.backoff <= 2):
            raise ValueError("Invalid timeout or retry configuration")
        return result


class ServiceError(Exception):
    def __init__(self, reason, retryable):
        super().__init__(reason)
        self.retryable = retryable


class Jobs:
    """One application process; duplicate job keys are coalesced in that process.

    Pending cases and export bytes are durable. Jobs themselves are not: after a
    restart, staff re-trigger processing or delivery through the API.
    """
    def __init__(self, path, settings, transport=None):
        self.path, self.settings = path, settings
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="verification")
        self.lock = threading.Lock()
        self.active = set()
        self.client = httpx.Client(timeout=httpx.Timeout(settings.timeout), transport=transport, trust_env=False)

    def submit(self, key, function, *args):
        with self.lock:
            if key in self.active or self.stop.is_set():
                return False
            self.active.add(key)
            self.pool.submit(self._run, key, function, args)
        return True

    def _run(self, key, function, args):
        try:
            function(*args)
        except Exception as exc:
            # Leave durable pending work retryable; never log environment values.
            log.error("Job %s stopped with %s; re-trigger after resolving the cause", key, type(exc).__name__)
        finally:
            with self.lock:
                self.active.discard(key)

    def busy(self, key):
        with self.lock:
            return key in self.active

    def close(self):
        self.stop.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.client.close()

    def request(self, url, **kwargs):
        try:
            response = self.client.post(url, **kwargs)
        except httpx.TimeoutException:
            raise ServiceError("Response timeout; result unknown", True) from None
        except httpx.RequestError:
            raise ServiceError("Service connection failure", True) from None
        if response.status_code >= 400:
            reason = f"HTTP {response.status_code}"
            try:
                reason += ": " + str(response.json().get("error", "Service rejected request"))[:300]
            except (ValueError, AttributeError):
                pass
            raise ServiceError(reason, response.status_code >= 500 or response.status_code == 429)
        if response.status_code != 200:
            raise ServiceError("Unexpected service response status", False)
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError
            return result
        except ValueError:
            raise ServiceError("Service returned invalid JSON object", False) from None

    def pause(self, attempt):
        return self.stop.wait(min(self.settings.backoff * 2 ** attempt, 2.0))

    def process_batch(self, batch_id, retry_failed=False):
        with connect(self.path, write=True) as db:
            if retry_failed:
                db.execute("UPDATE cases SET status='pending', failure_reason=NULL, retryable=0 "
                           "WHERE batch_id=? AND status='ocr_failed' AND retryable=1", (batch_id,))
            ids = [row[0] for row in db.execute("SELECT id FROM cases WHERE batch_id=? AND status='pending' ORDER BY row_number", (batch_id,))]
        for ident in ids:
            if self.stop.is_set():
                return
            self.process_case(ident)

    def process_case(self, ident):
        for attempt in range(self.settings.attempts):
            if self.stop.is_set():
                return
            with connect(self.path, write=True) as db:
                row = db.execute("SELECT * FROM cases WHERE id=?", (ident,)).fetchone()
                if row["status"] != "pending":
                    return
                db.execute("UPDATE cases SET ocr_attempts=ocr_attempts+1 WHERE id=?", (ident,))
            # Do not hold the database lock while calling a service.
            try:
                parsed = self.request(self.settings.ocr_url, json={"case_id": row["case_ref"], "image_ref": row["image_ref"]})
                required = ("id_number", "full_name", "dob", "issue_date", "confidence")
                if not all(key in parsed for key in required):
                    raise ServiceError("OCR response missing parsed fields", False)
            except ServiceError as exc:
                if exc.retryable and attempt + 1 < self.settings.attempts:
                    if self.pause(attempt):
                        return
                    continue
                reason = ("Retry budget exhausted: " if exc.retryable else "") + str(exc)
                with connect(self.path, write=True) as db:
                    db.execute("UPDATE cases SET status='ocr_failed', failure_reason=?, retryable=? "
                               "WHERE id=? AND status='pending'", (reason, int(exc.retryable), ident))
                return
            with connect(self.path, write=True) as db:
                db.execute("UPDATE cases SET status='ocr_done', parsed_fields=?, failure_reason=NULL, retryable=0 "
                           "WHERE id=? AND status='pending'", (json.dumps(parsed), ident))
            return

    def deliver(self, export_id):
        for attempt in range(self.settings.attempts):
            if self.stop.is_set():
                return
            with connect(self.path, write=True) as db:
                row = db.execute("SELECT * FROM exports WHERE id=?", (export_id,)).fetchone()
                if row is None or row["status"] == "delivered":
                    return
                db.execute("UPDATE exports SET status='pending',delivery_attempts=delivery_attempts+1 WHERE id=?", (export_id,))
            try:
                receipt = self.request(self.settings.onboarding_url, content=row["content"], headers={
                    "Idempotency-Key": export_id, "X-File-Name": row["file_name"], "Content-Type": "text/csv"})
                if (receipt.get("idempotency_key") != export_id or receipt.get("sha256") != row["sha256"]
                        or receipt.get("file_name") != row["file_name"] or not receipt.get("delivery_id")):
                    raise ServiceError("Receipt does not match durable export identity/content", False)
            except ServiceError as exc:
                if exc.retryable and attempt + 1 < self.settings.attempts:
                    if self.pause(attempt):
                        return
                    continue
                with connect(self.path, write=True) as db:
                    db.execute("UPDATE exports SET status='failed',failure_reason=? WHERE id=? AND status!='delivered'",
                               (str(exc), export_id))
                return
            with connect(self.path, write=True) as db:
                db.execute("UPDATE exports SET status='delivered',receipt=?,failure_reason=NULL WHERE id=?",
                           (json.dumps(receipt), export_id))
            return
