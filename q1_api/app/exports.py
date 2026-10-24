"""Export is a durable outbox: select cases, store bytes, advance states atomically."""
import csv
import hashlib
import io
import json
from uuid import uuid4

from .db import connect
from .validation import FIELDS


def create_export(path, batch_id):
    with connect(path, write=True) as db:
        rows = db.execute("SELECT * FROM cases WHERE batch_id=? AND status='stage2_approved' ORDER BY row_number", (batch_id,)).fetchall()
        if not rows:
            return None
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            values = {key: row[key] for key in FIELDS}
            parsed = json.loads(row["parsed_fields"]) if row["parsed_fields"] else {}
            # Export reviewed OCR identity values; preserve the original scan/reference.
            for key in ("id_number", "dob", "issue_date"):
                values[key] = parsed.get(key, values[key])
            values["applicant_name"] = parsed.get("full_name", values["applicant_name"])
            writer.writerow(values)
        content = output.getvalue().encode("utf-8")
        ident = str(uuid4())
        db.execute("INSERT INTO exports(id,batch_id,file_name,content,sha256,case_count) VALUES (?,?,?,?,?,?)",
                   (ident, batch_id, f"EXPORT-{ident}.csv", content, hashlib.sha256(content).hexdigest(), len(rows)))
        db.executemany("UPDATE cases SET status='exported' WHERE id=?", [(row["id"],) for row in rows])
        return ident


def export_summary(path, ident):
    with connect(path) as db:
        row = db.execute("SELECT id,batch_id,file_name,sha256,case_count,status,receipt,failure_reason,delivery_attempts,created_at "
                         "FROM exports WHERE id=?", (ident,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["receipt"] = json.loads(result["receipt"]) if result["receipt"] else None
    result["idempotency_key"] = ident
    return result
