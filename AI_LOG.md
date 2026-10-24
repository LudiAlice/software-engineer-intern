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
