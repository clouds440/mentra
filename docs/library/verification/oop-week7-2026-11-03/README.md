# Week 7 implementation evidence

All provider/model responses in tests are scripted or mocked. Actual local OCR and cached inference workers are identified by their suite. No live LLM calls were made. Private lecture images/text and database credentials are excluded.

| Evidence | Result / meaning |
| --- | --- |
| `baseline.txt` | Four original implementation regressions fail. Initial 20ms cold fixture was later calibrated to avoid framework overhead. |
| `calibrated-cold-baseline.txt` | Frozen `51924b1` executor still fails with 250ms startup and a 100ms query budget; the runner confirms this expected failure. |
| `core-fixed.txt`, `core-fixed-2.txt` | Initial correction and calibrated fixture progression, retained rather than overwritten. |
| `regression-1.txt`, `planner-1.txt`, `regression-2.txt` | Intermediate failures retained. Include an HTML placeholder bug, stale test assumptions, and one incorrectly targeted test edit; final runs supersede these outcomes. |
| `regression-3.txt` | 79 reader/recovery/image/planner tests pass. |
| `targeted-1.txt` | 31 OCR, embedding-worker, reranker and task-specific regressions pass. |
| `security-workflows.txt` | 65 migration, file-security, RAG ownership/archive/cache/provenance and workflow tests pass. Alembic reports no new upgrade operations after roundtrip. |
| `final-inference-planner.txt` | 81 tests pass, including dead-worker preparation, global deadlines, quota/integrity, fake provider image rejection, checkpoint privacy and scripted complete planner. |
| `final-targeted.txt` | All 14 final task-specific tests pass, including explicit citation-limit failure rather than silent omission. |
| `frontend-1.txt`, `frontend-2.txt` | Intermediate browser fixtures failed because they supplied diagrams after source caching / behind a catch-all API fixture; retained as superseded test evidence. |
| `frontend-diagram-3.txt` | Diagram decodes successfully after fixing fixture route precedence; checks natural width, not only a visible broken `<img>`. |
| `frontend-final.txt` | All 10 browser tests pass, including single upload-only OCR notice, processing refresh, historical failures and decoded diagrams. |
| `frontend-build.txt` | Production TypeScript/Vite build passes; existing large-chunk advisory remains. |
| `static-final.txt` | Static/diff checks; CRLF conversion advisories are not failed checks. |
| `local-comparison-1.txt` | Probe launcher failed before execution (script import path); superseded by module entry point. |
| `local-comparison-2.txt`, `local-comparison-3.txt` | Actual retained lecture, frozen scope/reader versus fixed code, three scope repeats, local OCR only. Third receipt confirms tool admission. |

The 14 final task tests overlap the larger groups; **do not add all counts and claim unique tests**. Fake network outage exceptions in passing workflow logs are intentional failure-injection checks.

Implementation hashes are recorded in `implementation-sha256.json`. Deployment and targeted source-repair receipts are added separately, with their own manifest. Earlier PDF/model benchmark evidence elsewhere in `/docs` remains unchanged.
