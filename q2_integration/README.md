# Module 2: OCR integration and export delivery

Add OCR, export, and delivery modules to `q1_api/app/`. Register the new endpoints on the existing `app.main:app` application. Keep the [fixed repository layout](../README.md#2-fixed-structure-and-naming).

Read the [Module 2 requirements](../README.md#4-module-2-ocr-integration-and-export-delivery), [OCR contract](../mock_ocr/README.md), and [account-opening contract](../mock_onboarding/README.md) before implementing the clients.

## Run without Docker

Start each service in a separate terminal from the repository root:

```bash
python3 mock_ocr/server.py
```

```bash
python3 mock_onboarding/server.py
```

```bash
python3 -m uvicorn app.main:app --app-dir q1_api --host 127.0.0.1 --port 8000
```

The defaults already point to the two local mock services. Use one API worker.

On Windows PowerShell, create a virtual environment once from the repository root
(Python 3.12 matches Docker and CI; Python 3.10+ is required):

```powershell
py -3.12 -m venv .venv-local
.\.venv-local\Scripts\python.exe -m pip install -r requirements.txt
```

Select an installed supported Python version if 3.12 is unavailable. The candidate's
local practice used 3.14; that does not replace validation under container Python 3.12.
In three separate terminals, all at the repository root:

```powershell
.\.venv-local\Scripts\python.exe mock_ocr/server.py
```

```powershell
.\.venv-local\Scripts\python.exe mock_onboarding/server.py
```

```powershell
.\.venv-local\Scripts\python.exe -m uvicorn app.main:app --app-dir q1_api --host 127.0.0.1 --port 8000
```

Keep these terminals running. Open http://127.0.0.1:8000/api/docs; `/` has no route.

Verify one batch through import, background OCR, both review stages, export, and submission to the account-opening service. Record retry and recovery evidence in [REFLECTION.md](../REFLECTION.md).

## Implemented workflow and configuration

Run the API as a single process/worker. Upload a multipart CSV to POST /api/batches, trigger POST /api/batches/{id}/process and poll GET /api/batches/{id}. Review OCR-complete cases through both stages using POST /api/cases/{id}/review. POST /api/batches/{id}/export persists a CSV and schedules delivery. GET /api/exports/{id} returns status/receipt, and GET /api/exports/{id}/download returns the saved CSV. GET /api/batches/{id}/exports lists existing exports.

The API reads environment variables directly; no local .env file is required or automatically loaded by application code. Defaults:

| Variable | Default |
|---|---|
| DATABASE_PATH | runtime/app.db relative to the repository root |
| OCR_URL | http://127.0.0.1:9100/ocr/parse |
| ONBOARDING_URL | http://127.0.0.1:9200/ingest |
| HTTP_TIMEOUT | 2 seconds |
| RETRY_ATTEMPTS | 5 total attempts per invocation |
| RETRY_BACKOFF | 0.2 seconds, exponential with a 2-second cap |

After an API restart, re-trigger /process for pending cases. Add ?retry_failed=true to include retryable OCR failures. Permanent 422 failures need corrected input. Re-trigger POST /api/exports/{id}/deliver for an existing failed/pending export; do not create a new identity to retry delivery. Preserve the receiver's idempotency records while retrying.

## Reproduce Q2 verification

From the repository root, with requirements installed:

```bash
python -m pytest q1_api/ -q
python q2_integration/scripts/verify_live.py
```

The second command starts and stops only its own local HTTP processes, uses temporary databases, injects accelerated delays and writes q2_integration/evidence/live-validation.json. Optional --temp-root selects an existing writable temporary directory and --output selects another report destination. It does not require Docker. Reports contain only supplied fictional data and source hashes. See REFLECTION.md for measured results and their limits.
