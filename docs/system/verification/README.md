# Verification evidence — 2026-11-03

Baseline commit: `c3f05376f96e8b3573daa3064dcf510f1a944c66`. Evidence is local/offline unless explicitly stated. No live LLM/provider calls. Raw logs include intentionally injected failures, native model progress and existing build warnings; read their final test summary rather than treating every logged exception as an acceptance failure.

## Accepted evidence

| Artifact | Result and scope |
| --- | --- |
| [complete-final-tests.txt](complete-final-tests.txt) | Final combined backend acceptance: **323 passed in 323.166 seconds**. Covers current schema and all affected consumers. |
| [baseline-final-regressions.txt](baseline-final-regressions.txt) | Expected negative control: six pre-fix tests, three failures/three errors. Uses frozen baseline source, not a checkout mutation. |
| [native-recovery-final-tests.txt](native-recovery-final-tests.txt) | 38 passed: device policy, actual spawned native-exit recovery, speech, embedding process and reranker; additional combined-run coverage follows. |
| [device-cpu-equivalence-final.json](device-cpu-equivalence-final.json) | Real cached E5 CPU outputs equal frozen implementation across ten language samples; reranker scores equal; actual supervised child outputs equal too. Model progress in the corresponding stderr file. |
| [speech-path-benchmark.json](speech-path-benchmark.json) | Five alternating paired real Base CPU INT8 runs, transcript equality and exact provider-operation counts. [Raw output](speech-path-benchmark-raw.txt) retains the original footer/resource warning. |
| [speech-path-final-benchmark.json](speech-path-final-benchmark.json) | Final repeat after supervisor/VAD edits: five paired trials, same transcript, zero provider operations for direct intake; 4.3529 s versus 4.2850 s medians. Empty corresponding stderr confirms clean process shutdown in this run. |
| [fts-generic-plans.json](fts-generic-plans.json) | Real PostgreSQL forced-generic-plan expression benchmark; matching result and before/after query plans. |
| [browser-durable-final.txt](browser-durable-final.txt) | Nine Chromium fixture tests passed: normal/chat answer sheets, held-pending job, same-revision failure recovery, confirmation, feedback and assisted scoring. |
| [browser-voice.txt](browser-voice.txt) | Five Chromium voice tests passed using direct multipart intake and no Files upload. |
| [cache-baseline.txt](cache-baseline.txt), [cache-final.txt](cache-final.txt) | Frozen cache dependency behavior fails fresh-read assertion; new implementation passes. |
| [notifications-final.txt](notifications-final.txt) | Behavioral stream checks pass: shared connection, background revision delivery, invalidation, owner cleanup/stale callback suppression. |
| [frontend-final-build.txt](frontend-final-build.txt) | TypeScript application/node checks and Vite build pass. Existing large-bundle warning remains. |
| [final-static-checks.txt](final-static-checks.txt) | Ruff F/E9 checks pass for application and audit experiment scripts. |
| [final-frontend-checks.txt](final-frontend-checks.txt) | Theme/UI conventions and behavioral cache/notification checks; final results recorded in this log. |
| [compose-config.txt](compose-config.txt) | Compose configuration validation passed without starting application services. |
| [disposable-cleanup.txt](disposable-cleanup.txt) | Named test PostgreSQL container/anonymous data volume and network removed; cached dependency image retained. |
| [final-review-checks.txt](final-review-checks.txt) | Final documentation links, historical-file preservation, whitespace and evidence consistency checks. |
| [integrity manifest](manifest.json) | SHA256 of preserved evidence, changed source and documentation at recording time; does not hash itself. Source worktree newline conversion may differ on another checkout; evidence/history files retain exact bytes through Git attributes. |

## Retained intermediate / superseded runs

| Artifact | Why retained / what supersedes it |
| --- | --- |
| `baseline-regressions.txt` | Initial five-case run included an invalid production-origin fixture; corrected baseline below. |
| `baseline-corrected.txt` | Five valid negative-control cases; final baseline adds explicit handoff-state coverage. |
| `focused-tests.txt` | Initial 22-test run included invalid production-origin fixture. Current combined run supersedes it. |
| `database-tests.txt` | Host runtime lacked the packaged tokenizer for a large-answer test. Packaged runtime/current combined run supplies the required asset. |
| `packaged-acceptance.txt` | 56 passed before expanded coverage. |
| `extended-tests.txt` | 233 tests; four stale assumptions: two outer transactions around concurrent-index migrations and two historical token-budget defaults. |
| `correction-tests.txt` | 15 tests; one schema-expansion fixture still used too small an explicit context. Corrected before the passing broad run. Production token budgets were not relaxed. |
| `final-tests.txt` | Earlier broad run: 237 passed; predates final chat source-queue extension. |
| `native-recovery-tests.txt` | 38 tests exposed charging embedding cold start against its short inference budget. Corrected by retaining the separate initialization budget; final native-recovery run passes. |
| `consumer-tests.txt` | 82 tests; one synthetic grading claim omitted its required owner and therefore never reached the intended timeout. Fixture corrected; combined acceptance supersedes it. |
| `durable-all-entrypoints-tests.txt` | 63 tests; downgrade test tried to execute new application queries against schema0039. Corrected to read canonical data directly while downgraded and run current repository only after reupgrade. |
| `browser-answer-sheets.txt`, `browser-durable-entrypoints.txt` | Eight passed in each earlier run; final nine-case run adds same-revision queued extraction failure. |
| `device-cpu-equivalence.json` | Earlier direct-only comparison; final file also checks real supervised children. |
| `frontend-build.txt`, `static-checks.txt` | Earlier passing checks; final named checks follow later edits. |
| `diff-check-stderr.txt` | Git newline-conversion notices from a successful whitespace check; final diff verification is separately recorded. |

Historic source migrations, model manifests, `docs/library/history/`, `docs/library/verification/` and the earlier speech guide were not rewritten. No old BGE result is used to certify the current E5/device behavior.

## Reproduction

Use an isolated PostgreSQL 17 database, the repository's installed backend dependencies/model assets, and `TEST_DATABASE_URL`. The recorded runs used disposable container `mentra-audit-tests-20261103` (host port55483), network `mentra-audit-verify-20261103`, and cached dependency image `mentra-backend:embedding-finished-20261103`; current backend source was mounted read-only at `/app`. These disposable resources are removed after verification. The existing cached image is retained.

From the repository root, set `PYTHONPATH=backend`, `PYTHONDONTWRITEBYTECODE=1`, `LOCAL_INFERENCE_DEVICE=cpu`, and point `TEST_DATABASE_URL` only at the disposable database. On this Windows environment the interpreter is `.venv\Scripts\python.exe`. Asyncio/spawn/Docker verification required local socket/pipe permission; a restricted host run hanging before asyncio initialization is not application evidence.

```powershell
# Negative control: expected nonzero exit and six failures/errors.
.venv\Scripts\python.exe -B -m testing.system_audit_baseline

# Current functional checks (run inside the packaged runtime for baked model assets).
python -B -m unittest tests.test_system_audit_regressions tests.test_inference_device tests.test_speech tests.test_speech_transient tests.test_assessments tests.test_chat_evidence_jobs tests.test_admission tests.test_embeddings tests.test_embedding_process tests.rag.test_reranker tests.rag.test_workflows tests.rag.test_lexical_migration tests.test_files tests.test_notifications tests.test_memory_summaries tests.test_chat_summaries tests.student_profile.test_profile tests.test_chat_assessments tests.test_memory_reconciliation tests.test_summarizer tests.vision.test_ocr tests.test_assessment_evaluation_latency
```

Prepare the ignored baseline experiment sources from the exact commit without changing the checkout:

```powershell
$baseline = 'c3f05376f96e8b3573daa3064dcf510f1a944c66'
New-Item -ItemType Directory -Force backend/.cache/system-audit | Out-Null
foreach ($pair in @(@('embeddings','backend/app/rag/embeddings.py'), @('reranker','backend/app/rag/reranker.py'), @('files_service','backend/app/files/service.py'))) {
  $content = git show "${baseline}:$($pair[1])"
  [IO.File]::WriteAllText((Join-Path (Get-Location) "backend/.cache/system-audit/pre_fix_$($pair[0]).py"), ($content -join "`n"), [Text.UTF8Encoding]::new($false))
}
```

Run from `/app` inside the same cached-model runtime, mounted current source and disposable database:

```text
python -B -m testing.verify_device_outputs
python -B -m testing.benchmark_fts_plans
python -B -m testing.benchmark_speech_paths .cache/system-audit/jfk.flac --baseline-source .cache/system-audit/pre_fix_files_service.py --repeats 5
```

For speech, limit the container to two CPUs and verify the public fixture's SHA256 from the implementation report before running. The fixture's source is `https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac`. No network delay is added in the accepted result. Timings depend on hardware, caches and concurrent load; transcript/operation counts and recovery assertions are the acceptance invariants.

From `frontend`, with installed dependencies/Chromium:

```powershell
npm run build
npx playwright test voice.spec.ts --config playwright.voice.config.ts
npx playwright test renovation-answer-sheets.spec.ts --config playwright.visual.config.ts
node scripts/audit-cache-check.mjs
node scripts/audit-notifications-check.mjs
npm run check:theme
npm run check:ui
```

Set `AUDIT_CACHE_BASELINE=1` for the intentionally failing cache negative control. Browser API fixtures make no live model calls. Do not sum overlapping intermediate test counts as unique tests.
