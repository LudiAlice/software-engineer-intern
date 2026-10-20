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
