import json
from pathlib import Path

from app.db import connect, initialize
from app.seed import seed_if_empty


def test_sample_seed_and_restart_preserve_existing_data(tmp_path):
    database = tmp_path / "seed.db"
    sample = Path(__file__).resolve().parents[2] / "data" / "account_applications.csv"
    first = seed_if_empty(database, sample)
    assert first["seeded"] and first["accepted"] == 43 and first["rejected"] == 7
    with connect(database, write=True) as db:
        assert db.execute("SELECT count(*) FROM cases WHERE status='pending'").fetchone()[0] == 43
        assert len(json.loads(db.execute("SELECT rejected_rows FROM batches").fetchone()[0])) == 7
        db.execute("UPDATE cases SET status='ocr_done' WHERE row_number=2")
    assert seed_if_empty(database, sample)["seeded"] is False
    with connect(database) as db:
        assert db.execute("SELECT count(*) FROM batches").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 43
        assert db.execute("SELECT status FROM cases WHERE row_number=2").fetchone()[0] == "ocr_done"


def test_existing_user_batch_prevents_sample_import(tmp_path):
    database = tmp_path / "existing.db"
    initialize(database)
    with connect(database, write=True) as db:
        db.execute("INSERT INTO batches(id,rejected_rows) VALUES ('user-batch','[]')")
    assert seed_if_empty(database, tmp_path / "unneeded.csv")["seeded"] is False
    with connect(database) as db:
        assert db.execute("SELECT id FROM batches").fetchone()[0] == "user-batch"
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0
