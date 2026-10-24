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

This module adds Q3 to the published Q1/Q2 baseline. CI is the chosen optional task and is being published separately; final remote-clone verification and the Actions result for the final commit remain to be checked. No final submission email has been sent.

## Subsequent candidate practice: Q3 publication preparation (2026-10-24)

The candidate has now performed guided local and container validation in the full learning checkout. The manual local batch accepted 43 rows and rejected seven; OCR ended with 37 successful and six failed cases. One case was approved through both stages, exported, delivered after two attempts and downloaded. The receiver debug response contained one ingestion for that export. A separate local smoke run exported 38 cases. These are separate runs, not contradictory counts.

All four Compose services became healthy. The candidate executed the smoke driver inside the API container through http://nginx; it completed with 37 exported, six ocr_failed and zero pending. The candidate then created backup-20261024T135048736350Z-ecabe311.sqlite3, stopped API writes and restored that named backup to /data/app.db. SQLite integrity_check returned ok. After restart, /api/ready returned true and export 236004da-065f-4a4c-be62-ecfaf65eb75a still reported delivered, case_count 37 and delivery_attempts 2.

The screenshot-supported observations and complete visible after-backup list are in q3_deploy/evidence/candidate-guided-validation-2026-10-24.json. The after list contains seven files, but the before list was cropped; a complete before/after retention check is still needed for submission evidence. No corruption was deliberately introduced before this restore, and only sampled business data was checked afterward. Existing containers/volumes were reused, so this is not final clean-clone verification. These observations update the candidate's practical experience; Q3 packaging/publication and final remote CI verification remain outstanding. Further independent practice is needed with Docker networking, operational commands and backup/restore.

### Measured backup retention listing

Nine online backups were made in the isolated validation volume. The ninth call produced the following complete listing; it removed the oldest listed backup and retained the new one.

| Before ninth backup | After ninth backup |
|---|---|
| backup-20261024T141128656296Z-f6ac4eb9.sqlite3 | backup-20261024T141128661260Z-700473f0.sqlite3 |
| backup-20261024T141128661260Z-700473f0.sqlite3 | backup-20261024T141128666006Z-896bc1d1.sqlite3 |
| backup-20261024T141128666006Z-896bc1d1.sqlite3 | backup-20261024T141128671324Z-2acc8715.sqlite3 |
| backup-20261024T141128671324Z-2acc8715.sqlite3 | backup-20261024T141128676003Z-b575680a.sqlite3 |
| backup-20261024T141128676003Z-b575680a.sqlite3 | backup-20261024T141128681051Z-617bcb4c.sqlite3 |
| backup-20261024T141128681051Z-617bcb4c.sqlite3 | backup-20261024T141128686313Z-3bea951f.sqlite3 |
| backup-20261024T141128686313Z-3bea951f.sqlite3 | backup-20261024T141128691807Z-1ec7b874.sqlite3 |

## Q3 design and publication-source validation

The API runs as an unprivileged user with one worker. Compose stores SQLite under /data in a named volume and starts dependent services only after their health checks pass. nginx preserves the complete /api/ and /ocr/ paths. Its 6 MiB request-body limit allows multipart framing around the application's 5 MiB file limit. Validation exercised both paths, an over-limit file returning 413 from the API, and a 7 MiB body returning 413 from nginx. The 3-second connect and 15-second read/send proxy timeouts bound inactive upstream operations; background OCR/delivery calls use the application's own shorter HTTPX timeouts and do not keep the process endpoint open.

Codex's publication-source run used a Git archive and a newly created isolated Compose project/volume. All 35 tests passed under Python 3.12.15 (one Starlette TestClient deprecation warning), including first-start seeding and preservation of existing data. The required bash smoke wrapper exercises a separate uploaded batch. The six row failures seen in the earlier default-settings smoke were not individually classified; this is distinct from the controlled Q2 fault-injection report. Final smoke results are recorded in publication-smoke.json.

Online backups use SQLite's backup API so committed WAL contents are included, then check integrity before renaming a temporary file. Restoration to a new temporary database returned integrity_check=ok and matched ordered contents of batches, cases and exports. The complete before/after retention listing above demonstrates removing the oldest of eight completed backups. Backups share the database volume and are not an off-machine disaster-recovery solution. Restoring an older database does not undo external receiver side effects; staff must reconcile receipts before redelivery.

Source hashes, test summary, smoke output and operations results are in q3_deploy/evidence/publication-validation.json, publication-smoke.json and publication-operations.json. These agent-run checks are separate from candidate screenshots. A final clone from GitHub and remote Actions still need verification after publication.

### First-start seeding and limits

Final requirement review identified that the previous deployment required the smoke driver to upload the sample. Codex added app.seed to fulfill seeded startup: before Uvicorn starts, a transaction imports the supplied CSV only if the database has no batches. A fresh volume receives one batch with 43 pending cases and seven rejection reasons; its ID is printed in startup logs. An existing user batch prevents import, and restart does not overwrite review/OCR progress. This affects the Docker entry command, not normal local API startup. The smoke script uploads its own additional batch. The candidate has been informed but has not yet reviewed this final addition, so seed.py and its two tests explicitly remain AI-generated code requiring candidate review.

Dependencies at the top level are pinned, but transitive versions and base image tags are not fully locked. Multiple API workers, durable receiver idempotency storage, off-host backups and production authentication are outside this exercise implementation. Operational commands are documented and have been practiced with guidance; independent fluency is not claimed.

## Optional CI and final verification boundary

The chosen optional task is CI. The separately committed workflow installs the pinned direct dependencies, runs the tests, validates Compose and builds application/mock images on every push and pull request. It uses read-only repository permissions and verified immutable references for checkout/setup-python. It does not deploy or run the smoke workflow; those checks are performed separately. Before final submission, match the remote green Actions run to the final commit and repeat startup/smoke from a GitHub clone with a fresh volume. This pre-push record does not assert a future remote outcome. No submission email has been sent.
