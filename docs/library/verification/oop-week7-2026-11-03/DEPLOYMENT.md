# Local Compose deployment and targeted lecture repair

The backend, frontend and five workers were recreated from images built at implementation commit `119e5fe93e97cac545ffaa9875c38082adb9db47`. Migration `20261103_0041` is applied. Backend and frontend health checks pass; the API readiness response reports database, embedding, Qdrant and worker checks OK. No hosted LLM calls were made.

| Verification | Result |
| --- | --- |
| Active work before restart | No running chat, ingestion, assessment generation/source or summary lease. [Counts](predeploy-active-work.json). |
| Private backup | PostgreSQL 17 custom-format archive, 1,079,408 bytes; `pg_restore --list` succeeded. SHA-256 `b00a05bff20712882ae2d7db48a6e570473331fcec931c9ed7b8230a4bebaab6`. Kept under ignored `.cache/rollbacks/`; original database and prior backups retained. The first launcher attempt failed before backup because stdin had a CR; the verified archive is a separate file. |
| Final images | [Build](docker-build.txt), [rollout](docker-rollout.txt), [running image IDs and revision labels](deployed-images.json), [readiness](health-ready.json). Workers share `mentra-backend:latest`. |
| Image tests | [20 tests passed on packaged backend](built-image-tests.txt), with only tests/fixtures mounted. [Three critical headless tests passed on deployed frontend](deployed-frontend.txt), using synthetic API fixtures. |
| Reindex scope | Only the affected Week 7 lecture; one successful attempt. [Queue receipt](targeted-repair-queued.json). |
| Original | Original PPTX bytes still match the immutable version hash, 235,677 bytes. Old citation still resolves to the prior generation. [Original hash check](original-integrity.json). |
| New publication | **51 stored chunks and 51 exact matching Qdrant points**. Four image files with matching SHA-256, OCR associated with slides **8, 24, 25 and 26**. The raw reader had 50 blocks; one block was split during chunking. [Source verification](deployed-source-verification.json). |
| Diagram delivery | Full-file `200` with matching hash, `206` for byte range, wrong owner `404` in an isolated test app with injected identities and actual file storage. No production authentication bypass was configured. |
| Complete ordered read | **2.396 seconds**; 26 outline sections, 27 cited body chunks, all four diagrams, no continuation. Receipt **19,925 bytes / 5,085 estimated tokens**, within existing result limits. One measurement, without model generation. |
| Local semantic search | **12.477 seconds separate preparation** for a fresh reranker worker, then **5.096 / 4.008 seconds active search** on two explicit lecture queries with real cached CPU E5 and reranker. Both returned three passages with successful reranking; one returned an associated diagram. Different queries from the historical trace; no paired whole-response latency claim. [Timings](deployed-search-final.json). An initial `/tmp` launcher lacked `PYTHONPATH` and ran no inference. |
| Cleanup | Removed the disposable PostgreSQL container/volume, its network, temporary runtime probe and superseded Mentra image tags. Only current Mentra backend/frontend `:latest` images remain. Application volumes, source records, earlier benchmark artifacts and private backups preserved. [Cleanup receipt](cleanup.json). |

Additional deployment finding: the configured Qdrant server reported **1.19.2**, and the repository's pinned Python client **1.15.1** emitted its minor-version compatibility warning. The warning was kept enabled. Actual dense search, count and exact point lookup passed in this release; the version drift remains a dependency upgrade item, rather than an untested pin change. Older image tags were cleaned up, so an application rollback should rebuild the prior revision; keep the additive 0041 schema and retained visuals.

This release does not claim a new live answer duration or new provider-generated answer quality. No private lecture images, text, credentials or original database bytes are committed. [Deployment hashes](deployment-sha256.json) are separate from the preserved implementation manifest.
