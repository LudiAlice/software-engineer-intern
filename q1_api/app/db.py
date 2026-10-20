"""Small SQLite persistence layer: one connection per unit of work."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def connect(path, *, write=False):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        if write:
            # Serialize read-modify-write operations (reviews and exports).
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                rejected_rows TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES batches(id),
                row_number INTEGER NOT NULL,
                case_ref TEXT NOT NULL,
                applicant_name TEXT NOT NULL,
                id_number TEXT NOT NULL,
                dob TEXT NOT NULL,
                issue_date TEXT NOT NULL,
                image_ref TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                parsed_fields TEXT,
                failure_reason TEXT,
                retryable INTEGER NOT NULL DEFAULT 0,
                ocr_attempts INTEGER NOT NULL DEFAULT 0,
                UNIQUE(batch_id, case_ref)
            );
            CREATE INDEX IF NOT EXISTS cases_batch_status ON cases(batch_id, status);
            CREATE TABLE IF NOT EXISTS exports (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES batches(id),
                file_name TEXT NOT NULL,
                content BLOB NOT NULL,
                sha256 TEXT NOT NULL,
                case_count INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                receipt TEXT,
                failure_reason TEXT,
                delivery_attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
