from contextlib import closing
import sqlite3

from app.backup import backup
from app.db import initialize


def test_online_backup_retention_and_restore(tmp_path):
    path = tmp_path / "live.db"
    initialize(path)
    destination = tmp_path / "backups"
    destination.mkdir()
    unrelated = destination / "keep.txt"
    unrelated.write_text("not a backup")
    # Keep a WAL connection open and write between backups.
    with closing(sqlite3.connect(path)) as live:
        for index in range(9):
            live.execute("INSERT INTO batches(id,rejected_rows) VALUES (?, '[]')", (str(index),))
            live.commit()
            result = backup(path, destination)
        assert len(result["before"]) == 7
        assert len(result["after"]) == 7
        assert unrelated.exists()
        with closing(sqlite3.connect(destination / result["backup"])) as restored:
            assert restored.execute("SELECT count(*) FROM batches").fetchone()[0] == 9
            assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
