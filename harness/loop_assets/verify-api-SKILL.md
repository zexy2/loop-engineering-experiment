---
name: verify-api
description: Verify the TaskFlow API against SPEC.md end-to-end before declaring any work done. Run after every implementation pass.
---

# Verifying the TaskFlow API

Never report progress based on code edits alone. Verify against a **running
server** every time:

1. Start clean: delete `taskflow.db`, start `uvicorn app.main:app --port 8000`,
   run `python -m app.seed`, capture both keys.
2. Re-read SPEC.md. Build a checklist of EVERY numbered endpoint and EVERY
   bullet in "Edge cases that must work".
3. Exercise each item with real HTTP requests (curl or a script you keep in
   `verify/`). For each: record expected vs actual status code, error envelope
   shape, and response body fields.
4. Specifically verify, every iteration:
   - auth: missing key 401, member on admin endpoint 403, cross-key access 404
   - validation: trimming, whitespace-only 422, unknown fields 422,
     malformed JSON 422, malformed UUID in path 404
   - tags: lowercasing, duplicate-after-lowercase 409, >10 tags 422
   - status transitions: done→todo 422, done→in_progress 200,
     double-complete 422 with "done" in the message
   - pagination: envelope shape, limit/offset bounds 422, ordering
   - filters: each one alone, combined, invalid values 422
   - bulk: mixed valid/invalid 207 with per-item statuses, >20 items 422
   - rate limiting: restart with RATE_LIMIT_PER_MINUTE=5 and prove 429 +
     all three headers; prove /v1/health stays exempt
5. Write the pass/fail table into PROGRESS.md, replacing the previous table.
6. Fix every failure found, then RE-RUN this whole skill from step 1.
7. Only when the table is 100% pass may you say the work is complete.
