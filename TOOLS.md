# Tool usage record

| Tool/source | Use | Affected files |
|---|---|---|
| OpenAI Codex | Baseline implementation, guided review, test assistance and module packaging | q1_api/app/, q1_api/tests/, documentation |
| Supplied exercise and mock contracts | Required behavior and repository structure | Q1 application and tests |
| Python sqlite3 | Persistence and transactions | q1_api/app/db.py, main.py |
| FastAPI/Pydantic | Request validation and HTTP routing | q1_api/app/main.py |
| pytest and HTTPX TestClient | API and validation tests | q1_api/tests/ |

See AI_LOG.md for material AI contributions. No actual local .env file is included.

## Q2 additions

- HTTPX: bounded-timeout service requests, request/response handling and deterministic MockTransport tests (q1_api/app/integrations.py and tests/test_integration.py).
- Python concurrent.futures/threading: background execution and single-process duplicate-job suppression.
- Python csv/json/hashlib/uuid and sqlite3: persisted CSV contents, export identity, content digests and receipts.
- Supplied mock_ocr and mock_onboarding services: independent HTTP fault-injection and debug-log verification. The verification script uses only fictional sample data, isolated ports and temporary databases.
- OpenAI Codex: implementation explanation, guided assertions, assessment scenarios, verification harness adaptation/execution, documentation and staged Git publication. Candidate participation and limits are recorded in AI_LOG.md.

## Q3 additions

- Docker Engine and Compose: isolated container builds, health-ordered service startup and persistent SQLite volumes. Python 3.12 is the container runtime; the candidate also exercised local startup under Python 3.14.
- nginx: path-preserving API/OCR reverse proxy, upload limit and upstream timeouts.
- Python sqlite3 backup API: live consistent copies, integrity checks and restore; pathlib/datetime handle timestamped files and seven-file retention.
- Git Bash: required smoke shell wrapper executed on Windows; PowerShell commands invoke the same Python drivers.
- OpenAI Codex: configuration/scripts, guided teaching, publication assembly, container tests and evidence recording. Candidate-operated steps are identified separately in AI_LOG.md and the evidence report.
