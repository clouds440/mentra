# PDF source fix: acceptance and runtime receipt

Implementation commit: `ed6197d26bb0b8872ca88b2ad7bce41e33e56449`. See the [analysis and acceptance report](../../PDF_Source_Viewer_Fix_2026-11-03.md). The pre-deployment `acceptance-manifest.json` remains unchanged; supplemental runtime evidence is hashed separately.

| Runtime check | Result / evidence |
| --- | --- |
| Rebuilt images | Backend and frontend built successfully from the implementation commit; both revision labels and all running worker labels match it. `docker-build.txt`, `runtime-after.json`. |
| Running services | API/frontend healthy; assessment, Files, RAG, events and summary workers running. Worker queues report healthy readiness. |
| Readiness | `/api/v1/health/ready` is ready; database, workers, AI configuration, embedding and Qdrant checks are OK. Configuration checks do not imply a live LLM request. `runtime-checks.json`. |
| Reported source after update | Still 66 saved/readable passages and 66 matching vector points, ready, no extraction error. Original file reference and published generation unchanged. Backend retains 51 notes; permanent per-page UI warnings removed. |
| Deployed frontend checks | All 16 Library/source fixture browser tests pass against the newly running Docker frontend, including the final cached-empty recovery and one upload-only notice. `browser-deployed-image.txt`. These tests intercept APIs and do not write user records or call hosted models. |
| Database version | The old running image was behind at 0038. Normal startup applied the previously committed 0039/0040 migrations; the valid lexical index and schema0040 were verified afterward. This PDF fix adds no migration of its own. |
| Backup | A private, Git-ignored pre-update custom-format PostgreSQL backup was taken and its archive catalog verified readable. `backup-receipt.json` records size/hash/path; the backup bytes and credentials are not committed. No restore was performed. |
| Restart boundary | Active chat, ingestion, generation and grading counts were zero before replacement. Application containers were recreated without deleting application volumes. `pre-restart-work.json`, `compose-update.txt`. |
| Test cleanup | Only disposable `mentra-pdf-tests-20261103`, its anonymous test-data volume and `mentra-pdf-verify-20261103` network were removed. |
| UI control | Native Computer Use was stopped by the user's physical Escape. No further Computer Use actions followed. The already-running command-line checks completed; no claim is made of a subsequent manual check of the user's browser session. |

Prior running image identities are in `runtime-before.json`. The old backend image expects schema0038 and cannot simply be restarted against0040. Prefer a schema-compatible previous source build for code rollback; any downgrade must follow the existing migration drain/preservation requirements and preserve the private backup. This update did not alter the reported Library source's original reference, generation, passage IDs or vector IDs.

Failed/intermediate acceptance runs remain indexed in the main report. The initial notes-disclosure UI was superseded by the user's upload-only warning requirement before release. The final UI has one selected-upload OCR notice, no persistent per-page lists, and actionable processing/read errors.
