# Tool usage record

| Tool/source | Use | Affected files |
|---|---|---|
| OpenAI Codex | Baseline implementation, guided review, test assistance and module packaging | q1_api/app/, q1_api/tests/, documentation |
| Supplied exercise and mock contracts | Required behavior and repository structure | Q1 application and tests |
| Python sqlite3 | Persistence and transactions | q1_api/app/db.py, main.py |
| FastAPI/Pydantic | Request validation and HTTP routing | q1_api/app/main.py |
| pytest and HTTPX TestClient | API and validation tests | q1_api/tests/ |

See AI_LOG.md for material AI contributions. No actual local .env file is included.
