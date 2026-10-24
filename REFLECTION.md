# Implementation reflection

## Q1 design and review

SQLite with WAL avoids an extra service for this exercise. Foreign keys and a unique (batch_id, case_ref) constraint preserve relationships. BEGIN IMMEDIATE keeps review validation and update inside one serialized write transaction.

Uploads are multipart UTF-8 CSV, limited to 5 MiB. Invalid documents return 422; invalid rows retain line numbers and reasons while valid rows are saved. Dates must be real YYYY-MM-DD values; issue dates earlier than birth dates are rejected, and equal dates are accepted. The first occurrence reserves a case reference within a batch, even if that row is invalid.

Review rules live in app/state_machine.py. Both rejection states are terminal. Invalid transitions return 409; malformed review parameters return 422. Q1 review tests prepare ocr_done explicitly; Q2 tests additionally exercise the complete OCR-to-delivery path. The guided return-action exercise is excluded from the required approve/reject contract.

## Q2 background processing and recovery

The API submits work to a two-thread ThreadPoolExecutor and returns 202 without waiting for the batch. A lock-protected active-key set prevents duplicate scheduling in one application process. SQLite stores cases, parsed fields and exports, but the job queue itself is in memory. The supported configuration is one API process/worker; multiple workers would require shared job coordination. Reads expose counts and processing state while work runs.

OCR requests run outside database write transactions. Timeout, connection failure, HTTP 429 and HTTP 5xx permit bounded retries; HTTP 422 does not. Exhausted attempts become ocr_failed with a reason and retryable flag. Staff can retry eligible failures using process?retry_failed=true; unreadable images require corrected input. An abrupt worker stop can leave a case pending. After restart, staff re-trigger processing; it is not an automatic startup recovery scheduler. The supplied OCR contract makes repeated parsing of the same image safe and deterministic.

Application defaults are a 2-second HTTPX timeout configuration, five total attempts per invocation, and a 0.2-second exponential retry base capped at 2 seconds. HTTPX timeouts constrain network operations rather than imposing one hard overall batch deadline. These conservative exercise defaults avoid waiting for the mock's 600-second delayed OCR response and 120-second delayed receipt. They are not a production latency calibration. The accelerated evidence run uses a 0.15-second timeout against a 0.6-second injected delay, eight attempts and a 0.01-second retry base; its results must not be presented as measurements of the default deployment settings.

## Q2 exports and delivery

One SQLite write transaction selects stage2_approved cases, constructs CSV bytes, persists an export identity/content/hash and marks selected cases exported. Previously exported cases and rejections are excluded. OCR identity fields are used with original-field fallback. A later approval creates a new export. The case's exported state means inclusion in a durable file, while the export's delivered state separately confirms a valid receipt.

The export UUID is the idempotency key because it names a persisted delivery, independent of process lifetime. Every retry uses the same stored bytes, filename and key. A new export gets a new key. Successful receipts must match the key, filename and content hash and contain a delivery ID before being stored. Failed delivery can be re-triggered with POST /api/exports/{id}/deliver; download reads the stored bytes without regenerating the export.

The supplied receiver deduplicates by key but retains keys only in memory. Retrying after its records are reset/restarted is outside the demonstrated deduplication guarantee. A production receiver would need durable idempotency storage. Candidate understanding of the selection/storage/key lifecycle was checked with three concrete scenarios; independent implementation under new requirements remains to be demonstrated.

## Verification

The earlier isolated Q1 commit passed 25 tests. On 2026-10-24, the Q1+Q2 publication checkout passed 32 tests (25 retained Q1 tests and seven Q2 tests), using the existing local virtual environment. This was not a fresh dependency installation or final clean-clone check. See q2_integration/evidence/verification-summary.json for runtime details. The seven Q2 tests cover transient/permanent OCR failures, nonblocking scheduling, lost receipts, export recovery, eligibility, pending-case recovery and mismatched receipts. A Starlette TestClient/HTTPX deprecation warning remains.

The reproducible live harness is q2_integration/scripts/verify_live.py. It starts the supplied mocks and API as independent local HTTP processes with isolated ports/databases; it never loads local configuration files. It runs a clean batch, kills its own API child while a second batch is still processing, restarts with the same database, and compares final status and parsed fields by case_ref. It then drives both review stages and export, forces a delayed post-ingestion response, and checks /debug/deliveries for one ingestion with repeated attempts. Full request logs, compared snapshots, configuration and source hashes are included in q2_integration/evidence/live-validation.json. This is a reproducible injected-failure experiment, not an exhaustive reliability guarantee.

## Q2 measured outcomes (2026-10-24)

- Input: 50 supplied synthetic rows; 43 accepted, seven rejected at CSV validation. Clean OCR finished with 38 ocr_done, five ocr_failed and zero pending. Those five failures were unreadable scans, distinct from the seven rejected input rows.
- Measurement method: classify every entry returned by the OCR mock's /debug/requests after the clean run. The 67 recorded requests included 38 ok, 14 error_500, ten hang and five unreadable. The observed request rates were 56.72%, 20.90%, 14.93% and 7.46%, respectively, using all 67 requests as denominator. Unreadable cases were 5/43 (11.63%) of accepted applications. Configured failure probabilities are not these observed rates; repeated attempts and unreadable cases affect the denominator.
- Recovery: when the harness killed its own API process, one case had reached ocr_done and 42 remained pending. After restart and re-trigger, final statuses AND parsed fields matched the clean run for every case_ref; 38 succeeded and five were unreadable. Full compared snapshots and both request logs are in the report.
- Delivery: all 38 OCR-successful cases were approved through both review endpoints and exported. Delayed post-ingestion response injection produced two delivery attempts with exactly one receiver ingestion. The export reached delivered, the receipt matched the persisted identity/content, and another export without new approvals returned no export.
- Timing: the process-trigger duration rounded to 0.0000 seconds at the harness's measurement precision. This is not a zero-latency claim or a performance benchmark; the dedicated blocked-OCR integration test separately checks return-before-completion behavior.
- Provenance: the report contains hashes of the exact application, mock, sample and harness sources used. Source hashes were rechecked after the run. Q3/CI and default container settings have not been validated by this module run.

## AI-generated code requiring further review

The baseline implementation and most tests were AI-assisted. The candidate reviewed Q1/Q2 flows, made guided test changes and correctly explained export/idempotency scenarios. Further independent practice is needed with thread scheduling, transaction concurrency and framework lifecycle behavior. Passing tests and reading explanations are not treated as proof of independent mastery. See AI_LOG.md for contributions.

## Incomplete work and next steps

This staged submission delivers Q1 and Q2. Q3 container operations, backup/restore, CI and final clean-clone verification remain for the next module. No final submission email has been sent. With additional time, review these remaining operational steps and production limitations rather than add unrelated features.
