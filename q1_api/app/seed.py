"""Import the supplied sample once when the container database has no batches."""
import json
import os
from pathlib import Path
from uuid import uuid4

from .db import connect, initialize
from .validation import FIELDS, parse_csv


def seed_if_empty(database, sample):
    initialize(database)
    with connect(database, write=True) as db:
        if db.execute("SELECT 1 FROM batches LIMIT 1").fetchone():
            return {"seeded": False, "reason": "Database already contains batches"}
        rows, rejected = parse_csv(Path(sample).read_bytes())
        batch_id = str(uuid4())
        db.execute("INSERT INTO batches(id,rejected_rows) VALUES (?,?)", (batch_id, json.dumps(rejected)))
        db.executemany(
            "INSERT INTO cases(id,batch_id,row_number,case_ref,applicant_name,id_number,dob,issue_date,image_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(str(uuid4()), batch_id, row["row_number"], *(row[key] for key in FIELDS)) for row in rows],
        )
    return {"seeded": True, "batch_id": batch_id, "accepted": len(rows), "rejected": len(rejected)}


if __name__ == "__main__":
    print(json.dumps(seed_if_empty(
        os.getenv("DATABASE_PATH", "/data/app.db"),
        Path(__file__).resolve().parents[2] / "data" / "account_applications.csv",
    )))
