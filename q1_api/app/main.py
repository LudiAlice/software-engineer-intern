"""HTTP boundary. Database and integration details live in separate modules."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import json
import os
import sqlite3
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict

from .db import connect, initialize
from .state_machine import STATUSES, next_status
from .validation import FIELDS, parse_csv

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


def create_app(database_path=None):
    path = str(database_path or os.environ.get("DATABASE_PATH") or
               Path(__file__).resolve().parents[2] / "runtime" / "app.db")

    @asynccontextmanager
    async def lifespan(application):
        initialize(path)
        yield

    application = FastAPI(title="Identity Verification", lifespan=lifespan)
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
        return batch_summary(path, batch_id)

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

    return application


app = create_app()
