# Implementation reflection

## Design decisions

SQLite with WAL avoids an extra service for this exercise. Foreign keys and a unique (batch_id, case_ref) constraint preserve relationships. BEGIN IMMEDIATE keeps review validation and update inside one serialized write transaction.

Uploads are multipart UTF-8 CSV, limited to 5 MiB. Invalid documents return 422; invalid rows retain line numbers and reasons while valid rows are saved. Dates must be real YYYY-MM-DD values; issue dates earlier than birth dates are rejected, and equal dates are accepted. The first occurrence reserves a case reference within the batch, even if that row is invalid.

Review rules live in app/state_machine.py. Both rejection states are terminal. Invalid transitions return 409; malformed review parameters return 422. OCR is not invoked by this Q1-only version: review tests prepare ocr_done explicitly.

## Verification

The isolated module passed 25 pytest tests covering import validation, sample counts, pagination/filtering, successful review, invalid and repeated transitions, terminal rejections, concurrent review and missing resources. A Starlette TestClient/HTTPX deprecation warning remains.

## AI-generated code requiring further review

The candidate has reviewed Q1 with Codex and made guided code/test changes. Further independent practice is needed with transaction concurrency and framework lifecycle behavior. See AI_LOG.md for provenance and contributions.

## Incomplete work and next steps

This commit implements Q1 only. OCR integration/recovery, export delivery, container operations and CI are not delivered here. Mock measurements, recovery evidence and backup evidence will accompany the corresponding modules. With additional time, verify those modules and the final clean-clone workflow rather than add unrelated features.
