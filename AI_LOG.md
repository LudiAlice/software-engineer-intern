# AI interaction record

## Q1 implementation and review

- Tool: OpenAI Codex.
- Prompt summary: implement the Gekko exercise, then explain the core API and guide candidate-led validation and test changes. Publish Q1 separately after review.
- Affected files: q1_api/app/{main,db,validation,state_machine,__init__}.py, q1_api/tests/, requirements.txt and Q1 documentation.
- Adopted output: substantial AI-generated baseline API, SQLite persistence, CSV validation, review transition rules and tests.
- Candidate changes: guided date-order validation; tests for equal dates, invalid dates, invalid review stages and repeated review. Codex supplied some assertion corrections and post-request state checks. These changes are not claimed as entirely unaided work.
- Review evidence: candidate traced batch/case identifiers, query responses, state transitions and transactions, and completed a guided return-and-review exercise. The extra return action and its tests are excluded from this submission to preserve the required API contract.
- Rejected/adjusted output: full local Q2/Q3 implementation is excluded from this module commit; shared application code is reduced to a standalone Q1. The complete local project remains preserved.
- Verification: the isolated Q1 version passed 25 tests. This does not establish independent mastery of every implementation detail.

This commit packages previously developed and subsequently reviewed work by module; it does not represent a claim that all code was independently written at commit time. Further module records will be added with their submissions.

## Q2 implementation, candidate review and staged publication (2026-10-24)

- Tool: OpenAI Codex. Prompt summary: explain the existing Q2 data flow and tests, assess the candidate's understanding, verify the submission version, update provenance records and publish Q2 separately before studying Q3.
- Adopted output: substantial AI-assisted implementation of HTTP clients, bounded retries, background jobs, durable CSV exports, idempotent delivery and integration tests. Codex also prepared and executed the isolated live verification harness and assembled this module commit.
- Candidate participation: traced request parameters and database fields through OCR, review, export, download and delivery; reviewed fixture injection, mocked responses, counters and restart behavior. The final OCR request-count assertion (`len(calls) == 5`) was added during guided work after Codex supplied the expected assertion; this is not claimed as unaided test design.
- Observed understanding: in a final scenario without supplied answers, the candidate correctly selected only stage-2-approved cases, identified the exports table as file storage, explained stable content/key on retries and receiver deduplication, and selected a new export ID for later approvals. This supports understanding of that flow, not independent mastery of the entire implementation.
- Adjusted output: only Q2 code/tests and reproducible evidence are added to the published Q1 baseline. The learning-only return action remains excluded. Q3 deployment, backup and CI work remains outside this module commit. The live harness was narrowed to Q2 and records source hashes.
- Verification responsibility: test execution and live fault-injection measurements were performed by Codex. The publication checkout passed 32 tests; the independent-service run confirmed matching clean/recovered states and one ingestion after two delivery attempts. Details and limitations are in REFLECTION.md and q2_integration/evidence/live-validation.json. The candidate reviewed the mechanisms; no claim is made that they independently authored or executed every validation step.

## Candidate-led local and container practice (2026-10-24; Q3 publication preparation)

- Prompt summary: explain Docker/Compose, health checks, nginx, SQLite backup direction and CI, then guide the candidate through running the existing full local project.
- Codex supplied explanations and commands. After the old virtual environment could not locate its base Python in the candidate's terminal, Codex prepared a separate Python 3.14 local environment and adjusted local startup documentation. Docker remains configured for Python 3.12. This was environment repair, not a business-logic rewrite.
- The candidate personally started the three local services, imported the sample, triggered OCR, approved one case through both stages, exported and downloaded the CSV, and inspected the receiver's single ingestion after two attempts. They then ran the local smoke driver.
- The candidate built and started the four Compose services, ran the smoke driver through nginx, created an online backup, stopped the API, restored the explicitly named backup using SQLite's backup API, restarted the API and checked readiness and the persisted export. Commands were supplied by Codex; this is guided execution, not unaided deployment or original implementation.
- The candidate correctly explained source-to-destination copying for s.backup(d) after discussion. Docker/operations remain new topics requiring independent repetition; successful commands do not establish mastery.
- Codex transcribed screenshot-supported outcomes into q3_deploy/evidence/candidate-guided-validation-2026-10-24.json. Existing Docker storage was reused. Final publication-source validation, complete retention evidence, clean-clone verification and remote CI are separate checks and are not claimed by these screenshots.

## Q3 implementation and publication verification (2026-10-24)

- Adopted AI-assisted code: Dockerfile, Compose health checks and persistent SQLite storage, nginx routing/limits, online backup and retention, the backup test, smoke driver, shell wrappers and operations documentation. The candidate studied these mechanisms and performed the guided exercises above; independent operational fluency remains to be developed.
- Codex packaged Q3 on the published Q1/Q2 baseline without the learning-only return action. It also made Q2 startup instructions usable from the repository root and documented Windows virtual-environment choices. The original local project was preserved.
- Validation: Codex built an archive of the staged submission in a new Compose project and volume, ran all 33 pytest tests under Python 3.12.15 and executed the required bash smoke wrapper through nginx. It separately checked both proxy paths, upload limits, nine online backups with seven retained files, and restoration into a new database with matching ordered contents of all three business tables. Reports and normalized source hashes are in q3_deploy/evidence/publication-*.json.
- A Windows access-control error prevented Docker from traversing an old local pytest cache in the packaging checkout. Building the staged Git archive avoided local generated files; no permissions on the candidate's files were reset. A Starlette TestClient deprecation warning remains. Final remote-clone and CI checks are separate from this staged-source validation.
- Final requirement review found a gap: the earlier Docker startup initialized only schema, whereas the exercise requests a seeded system. Codex added app/seed.py, two tests and a Docker entry command that imports the sample only when no batches exist. The candidate was informed during handoff but has not yet reviewed this addition. It is not claimed as candidate-written or understood. The revised container passed 35 tests and fresh-volume seeding produced one batch with 43 accepted cases; existing records remain unchanged on subsequent initialization.

## Optional CI publication (2026-10-24)

- Codex supplied the GitHub Actions workflow and explained triggers, dependency installation, pytest, Compose validation/build and failure propagation to the candidate. Candidate independent workflow authoring is not claimed.
- The workflow runs on push and pull request, with a manual trigger, read-only contents permission, pinned official Action commits and Python 3.12. Codex verified that both pinned commits exist in the official actions repositories before publication.
- This separate commit adds CI after the Q3 commit. Local 35-test success and image builds precede publication, but they do not prove a remote Actions result. The final commit must be matched against its GitHub Actions run after push; that result and the final clone checks are reported separately rather than invented in a pre-push log.
