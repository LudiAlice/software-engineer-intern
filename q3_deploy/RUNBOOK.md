# Operations runbook

## Start and check

From the repository root, install Python 3.10+ dependencies with `python -m pip install -r requirements.txt`.
For containers, use Docker Engine + Compose v2. From `q3_deploy/` run:

```bash
docker compose --env-file .env.example up --build -d --wait
bash scripts/smoke_test.sh
docker compose --env-file .env.example ps
```

The example configuration contains no secrets. No local `.env` is required. Plain
`docker compose up --build` also uses equivalent defaults when no overrides exist.
Do not print, commit or package a local `.env`. API docs: http://localhost:8080/api/docs.
On first container startup, an empty database receives the provided sample as a
pending batch; its ID appears in API startup logs. Existing batches prevent
re-import on restart. The smoke driver uploads a separate batch on each run.
SQLite persists in `app_data`.
Run **one API process**: job coalescing is in-process; SQLite transactions protect
reviews/exports. For local (non-Docker) use, run the two mock scripts in separate
terminals, then `python -m uvicorn app.main:app --app-dir q1_api --port 8000`.
Defaults use loopback ports 9100/9200 and `runtime/app.db`; optional configuration is
through environment variables only. Test with `python -m pytest q1_api/` and
`python q3_deploy/scripts/smoke_test.py --base http://127.0.0.1:8000`.

## Logs and failure diagnosis

Use `docker compose --env-file .env.example logs --tail=80 api` for job errors.
Avoid dumping full configuration or environment values. `/api/health` is liveness;
`/api/ready` checks the actual database schema. Inspect
`GET /api/batches/{id}/cases?status=ocr_failed` for row-level reasons.
An unreadable scan (422) is terminal for that image. Transient failures exhausted
after five attempts can be retried with
`POST /api/batches/{id}/process?retry_failed=true`. After a worker restart, use
`POST /api/batches/{id}/process`; unfinished cases are still `pending`.
`GET /api/batches/{id}/exports` lists durable exports. Re-deliver a failed/pending
export with `POST /api/exports/{id}/deliver`; do not create a new key for a retry.
The mocks keep deduplication records only in memory: restarting/resetting the
account-opening mock loses that protection. Do not reset it during delivery tests.

## Backup and restore

Run `bash scripts/backup.sh` while the system is running. It uses SQLite's backup
API, checks integrity, prints before/after filenames and keeps the newest seven
`backup-*.sqlite3` files under `/data/backups` (the persistent volume). These backups
share the data volume; off-machine disaster recovery is outside this exercise.

For restore, choose a verified backup filename from the backup output. Stop API
writes, restore via SQLite, then restart. Replace `BACKUP_NAME` below; do not use a
wildcard. Keep the onboarding mock running so its receipts survive.

```bash
docker compose --env-file .env.example stop api
docker compose --env-file .env.example run --rm --no-deps api python -c "import sqlite3; s=sqlite3.connect('file:/data/backups/BACKUP_NAME?mode=ro',uri=True); d=sqlite3.connect('/data/app.db'); s.backup(d); print(d.execute('PRAGMA integrity_check').fetchone()[0]); d.close(); s.close()"
docker compose --env-file .env.example start api
```

Check `/api/ready` and batch counts afterward. An older snapshot may predate later
deliveries: reconcile with external receipts before re-exporting restored approvals.
Do not delete volumes as part of routine shutdown (`docker compose stop` preserves them).
Evidence and current verification limits are in `../REFLECTION.md`.

## Windows commands from the repository root

Use `docker compose --env-file q3_deploy/.env.example -f q3_deploy/docker-compose.yml`
as the Compose prefix for the commands above. For online backup, append
`exec -T api python -m app.backup`; for smoke testing, append
`exec -T api python q3_deploy/scripts/smoke_test.py --base http://nginx`.
The shell wrappers and these PowerShell commands call the same Python modules.
