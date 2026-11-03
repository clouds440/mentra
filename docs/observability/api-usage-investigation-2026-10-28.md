# October 28, 2026 API usage investigation

Investigated November 1, 2026. No provider requests were made during this investigation. No credentials were printed or changed.

## Finding

The strongest supported explanation is repeated configured-model development testing by the coding agent during the semantic orchestration migration. The surviving coding-session record proves seven full 64-episode batches, a six-episode smoke run, and individual diagnostic reruns. These were actual DeepSeek requests with simulated domain effects; simulated tools did not make the model calls free or mocked.

The screenshot reports **1,024 requests, 6,809,149 tokens, $0.63**, with API Key set to **All**. It does not establish which individual key incurred all the usage. Its timezone is unknown; times below are converted from recorded UTC to Asia/Karachi.

## Evidence

| Source | Confirmed result |
| --- | --- |
| `logs/backend/backend-2026-10-28.log` | 21 individual `model.usage` events; 97,916 input + 3,954 output = 101,870 tokens. 39,168 input tokens were cached, already included in input totals. Sources: 17 chat, 3 chat evidence, 1 event admission. |
| `.cache/semantic-optimized-final.json` | Final 64-episode corpus contains 122 usage-bearing model responses: 840,471 input + 24,034 output = 864,505 tokens. These are recorded provider counters, not estimates. |
| Coding-session history | Seven separately launched full 64-episode corpus runs, plus smoke and individual reruns. Earlier unsuccessful candidates incurred real usage too. |
| `backend/scripts/verify_semantic_orchestration.py` | Uses configured `MentraLLM`/`ModelFactory`; each episode can invoke the provider several times. Final script sets provider retries to zero and runs two episodes concurrently. Ordinary orchestration rounds still create multiple requests. |
| `docs/orchestration/audits/semantic-orchestration-verification-2026-10-28.md` | Explicitly describes real `deepseek-flash` evaluation, plus actual generation/grading and memory-capture checks. Its 64/64 acceptance figure describes the final corpus, not the total number of development episodes executed. |

The app-log and final-corpus counts are separate evidence sets; neither should be treated as a complete provider ledger. Do not multiply the final corpus numbers by seven and present that as measured usage: earlier versions differed.

## Reconstructed full-corpus timeline

| Launch time, Pakistan | Output | Reported episode result |
| --- | --- | --- |
| 21:49:33 | `semantic-model-evaluation.json` (default) | 37/64 |
| 21:53:04 | `semantic-model-v3.1.json` | 61/64 |
| 21:58:45 | `semantic-model-v3.2.json` | 60/64 |
| 22:06:02 | `semantic-model-optimized.json` | 58/64 |
| 22:14:13 | `semantic-model-candidate.json` | 58/64 |
| 22:30:45 | `semantic-model-final.json` | 63/64 |
| 23:21:54 | `semantic-optimized-final.json` | 64/64 |

The smoke run launched at 21:48:34 and completed 6/6. Additional onboarding, quiz and paper diagnostics were launched between the full runs. Earlier that day the coding agent also ran English/Urdu questionnaire provider checks. A real generation/grading check launched at 23:36:56; automatic memory capture was checked as part of release verification.

Primary historical evidence: `C:/Users/Xclouds/.codex/sessions/2026/10/27/rollout-2026-10-27T16-35-12-01a17d24-9818-7bd3-9656-0ca551ec4f05.jsonl`. This session continued on October 28. Request launches and tool results were inspected directly, rather than relying only on the release narrative.

At 23:47:14, the coding agent launched cleanup deleting obsolete `semantic-*.json` outputs and diagnostic logs, retaining the final corpus and selected acceptance logs. The session preserves launches/results, but earlier complete per-call token records are no longer available in those scratch files.

## Logging gap

The daily file is 67,108,781 bytes, just below its 67,108,864-byte limit. Its last valid record is **17:18:00 UTC / 22:18:00 Pakistan**. `backend/app/core/observability/files.py` rejects further writes when the daily file would exceed the limit; it does not create another segment. This leaves later activity unrecorded in that daily file. The file also contains three invalid JSON lines excluded from aggregation.

Consequently, the 21 logged usage events do not prove that Mentra only made 21 calls. The later final corpus alone proves considerably more. Docker Desktop's engine was not running during this investigation, so retained container stdout could not be inspected.

## Key reuse checks and limits

- Current `.env` config selects `deepseek-flash` at `https://api.deepseek.com`.
- Compared the current key in memory against 4,304 eligible source/config files under `C:/Users/Xclouds/Documents`, excluding dependency/build/cache/log and game directories. Only `mentra/.env` matched. This was a bounded local scan, not a whole-disk or remote audit.
- No currently Git-tracked Mentra file contained the current key. `git log --all -- .env` returned no commits for that path; this does not prove every historical file was free of credentials.
- Neither `C:/Users/Xclouds/.codex/config.toml` nor `auth.json` contained this key. No environment variable in this investigation process exactly matched it.
- Current-key checks cannot establish which key was configured historically, detect another machine, or rule out copied/stolen credentials.
- No provider account/request export, per-key breakdown, source-IP records, or dashboard timezone was available. Exact reconciliation to 1,024 calls and 6,809,149 tokens remains unproven.

## Conclusion and prevention

Development evaluation is a documented, substantial source of this usage and is consistent with the evening spike. There is no positive evidence of outside use in the local sources checked, but outside use cannot be excluded. An individual-key provider export would be needed to close the accounting gap.

Useful follow-up changes are a separate development-test key, an explicit request/token allowance for paid evaluation runs, preserving cumulative usage for failed and successful runs, and segmented daily logs that continue recording after 64 MiB. These changes were not implemented as part of this read-only investigation.
