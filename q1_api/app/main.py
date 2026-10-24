"""HTTP boundary. Database and integration details live in separate modules."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import json
import os
import sqlite3
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, UploadFile, Response
from pydantic import BaseModel, ConfigDict

from .db import connect, initialize
from .state_machine import STATUSES, next_status
from .validation import FIELDS, parse_csv
from .integrations import Jobs, Settings
from .exports import create_export, export_summary

MAX_UPLOAD = 5 * 1024 * 1024


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    stage: Literal[1, 2]
    decision: Literal["approve", "reject"]


def require_batch(db, batch_id):
    batch = db.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    if batch is None:
        raise HTTPException(404, "Batch not found")
    return batch


def batch_summary(path, batch_id):
    with connect(path) as db:
        batch = require_batch(db, batch_id)
        counts = dict.fromkeys(STATUSES, 0)
        for row in db.execute("SELECT status, count(*) n FROM cases WHERE batch_id=? GROUP BY status", (batch_id,)):
            counts[row["status"]] = row["n"]
        rejected = json.loads(batch["rejected_rows"])
        return {"id": batch_id, "created_at": batch["created_at"], "accepted": sum(counts.values()),
                "rejected": len(rejected), "rejected_rows": rejected, "counts": counts}


def create_app(database_path=None, *, settings=None, transport=None):
    path = str(database_path or os.environ.get("DATABASE_PATH") or
               Path(__file__).resolve().parents[2] / "runtime" / "app.db")

    @asynccontextmanager
    async def lifespan(application):
        initialize(path)
        application.state.jobs = Jobs(path, settings or Settings.from_environment(), transport)
        try:
            yield
        finally:
            application.state.jobs.close()

    application = FastAPI(title="Identity Verification", lifespan=lifespan,
                          docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    application.state.database_path = path

    @application.get("/api/health")
    def health():
        return {"status": "ok"}

    @application.get("/api/ready")
    def ready():
        try:
            with connect(path) as db:
                db.execute("SELECT count(*) FROM batches").fetchone()
        except sqlite3.Error:
            raise HTTPException(503, "Database unavailable") from None
        return {"ready": True}

    @application.post("/api/batches", status_code=201)
    async def import_batch(file: UploadFile):
        payload = await file.read(MAX_UPLOAD + 1)
        await file.close()
        if len(payload) > MAX_UPLOAD:
            raise HTTPException(413, "CSV exceeds 5 MiB")
        try:
            rows, rejected = parse_csv(payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        batch_id = str(uuid4())
        with connect(path, write=True) as db:
            db.execute("INSERT INTO batches(id,rejected_rows) VALUES (?,?)", (batch_id, json.dumps(rejected)))
            db.executemany(
                "INSERT INTO cases(id,batch_id,row_number,case_ref,applicant_name,id_number,dob,issue_date,image_ref) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                [(str(uuid4()), batch_id, row["row_number"], *(row[key] for key in FIELDS)) for row in rows],
            )
        return batch_summary(path, batch_id)

    @application.get("/api/batches/{batch_id}")
    def get_batch(batch_id: str):
        result = batch_summary(path, batch_id)
        result["processing"] = application.state.jobs.busy("ocr:" + batch_id)
        return result

    @application.get("/api/batches/{batch_id}/cases")
    def list_cases(batch_id: str, status: str | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        if status is not None and status not in STATUSES:
            raise HTTPException(422, "Unknown case status")
        where, args = "batch_id=?", [batch_id]
        if status is not None:
            where += " AND status=?"
            args.append(status)
        with connect(path) as db:
            require_batch(db, batch_id)
            total = db.execute(f"SELECT count(*) FROM cases WHERE {where}", args).fetchone()[0]
            rows = db.execute(f"SELECT * FROM cases WHERE {where} ORDER BY row_number LIMIT ? OFFSET ?",
                              [*args, page_size, (page - 1) * page_size]).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["parsed_fields"] = json.loads(item["parsed_fields"]) if item["parsed_fields"] else None
            item["retryable"] = bool(item["retryable"])
            items.append(item)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @application.post("/api/cases/{case_id}/review")
    def review(case_id: str, body: Review):
        with connect(path, write=True) as db:
            case = db.execute("SELECT status FROM cases WHERE id=?", (case_id,)).fetchone()
            if case is None:
                raise HTTPException(404, "Case not found")
            try:
                target = next_status(case["status"], body.stage, body.decision)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            db.execute("UPDATE cases SET status=? WHERE id=? AND status=?", (target, case_id, case["status"]))
        return {"id": case_id, "status": target}

    @application.post("/api/batches/{batch_id}/process", status_code=202)
    def process_batch(batch_id: str, retry_failed: bool = False):
        result = batch_summary(path, batch_id)
        jobs = application.state.jobs
        result["scheduled"] = jobs.submit("ocr:" + batch_id, jobs.process_batch, batch_id, retry_failed)
        result["processing"] = jobs.busy("ocr:" + batch_id)
        return result

    @application.post("/api/batches/{batch_id}/export", status_code=202)
    def export_batch(batch_id: str):
        with connect(path) as db:
            require_batch(db, batch_id)
        ident = create_export(path, batch_id)
        if ident is None:
            with connect(path) as db:
                pending = [row[0] for row in db.execute("SELECT id FROM exports WHERE batch_id=? AND status!='delivered'", (batch_id,))]
            return {"export": None, "message": "No newly approved cases", "undelivered_exports": pending}
        jobs = application.state.jobs
        jobs.submit("delivery:" + ident, jobs.deliver, ident)
        return {"export": export_summary(path, ident)}

    @application.get("/api/batches/{batch_id}/exports")
    def list_exports(batch_id: str):
        with connect(path) as db:
            require_batch(db, batch_id)
            ids = [row[0] for row in db.execute("SELECT id FROM exports WHERE batch_id=? ORDER BY created_at,id", (batch_id,))]
        return {"items": [export_summary(path, ident) for ident in ids]}

    @application.get("/api/exports/{export_id}")
    def get_export(export_id: str):
        result = export_summary(path, export_id)
        if result is None:
            raise HTTPException(404, "Export not found")
        return result

    @application.post("/api/exports/{export_id}/deliver", status_code=202)
    def retry_delivery(export_id: str):
        result = get_export(export_id)
        jobs = application.state.jobs
        result["scheduled"] = (result["status"] != "delivered" and
                               jobs.submit("delivery:" + export_id, jobs.deliver, export_id))
        return result

    @application.get("/api/exports/{export_id}/download")
    def download(export_id: str):
        with connect(path) as db:
            row = db.execute("SELECT file_name,content FROM exports WHERE id=?", (export_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Export not found")
        return Response(bytes(row["content"]), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{row["file_name"]}"'})

    return application


app = create_app()
