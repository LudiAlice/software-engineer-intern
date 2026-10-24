"""Online SQLite backup; retention only removes our completed backup files."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


def backup(database_path, destination):
    source = Path(database_path).resolve(strict=True)
    directory = Path(destination).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    before = sorted(p.name for p in directory.glob("backup-*.sqlite3"))
    name = "backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    temporary, final = directory / (name + ".tmp"), directory / (name + ".sqlite3")
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(temporary)) as target:
                src.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity check failed")
        temporary.replace(final)
    finally:
        temporary.unlink(missing_ok=True)
    candidates = sorted(directory.glob("backup-*.sqlite3"), key=lambda p: p.name, reverse=True)
    for old in candidates[7:]:
        old.unlink()
    return {"backup": final.name, "before": before,
            "after": sorted(p.name for p in directory.glob("backup-*.sqlite3"))}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=os.getenv("DATABASE_PATH", "/data/app.db"))
    parser.add_argument("--directory", default="/data/backups")
    args = parser.parse_args()
    print(json.dumps(backup(args.database, args.directory), indent=2))
