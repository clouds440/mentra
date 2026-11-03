# Baseline system audit findings — 2026-11-03

This register reconstructs the findings delivered in the audit discussion against commit `c3f05376f96e8b3573daa3064dcf510f1a944c66`. It records the pre-fix state, not current behavior. It is not a verbatim copy of that discussion. Follow the [implementation report](../System_Audit_Implementation_2026-11-03.md) for disposition and evidence.

| ID | Priority | Observed gap | Consequence | Principal baseline source |
| --- | --- | --- | --- | --- |
| F01 | P1 | Chat evidence accepts incomplete response outcomes; claim validation can throw before retiring a stale source; replay inserts duplicate queue PKs. | Partial answers become evidence candidates; a bad source repeatedly interrupts queue progress. | `backend/app/langchain/repositories/evidence.py` |
| F02 | P1 | Files provider uses `FILES_ENVIRONMENT or APP_ENV`, but service upload IDs and cleanup use `APP_ENV`. | Explicit environment overrides disagree with provider ownership and cleanup boundaries. | `backend/app/files/service.py` |
| F03 | P1 | Speech pipe submission/receipt can block outside its polling timeout; speech upload validation decodes natively in the API process. | A nonreading child or stuck decoder defeats the intended operation bound. | `backend/app/speech/service.py`, `backend/app/files/service.py` |
| F04 | P2 | Replacing a draft answer sheet leaves its earlier file binding live. | Inaccessible superseded originals remain retained indefinitely. | `backend/app/assessments/repositories/postgres.py` |
| F05 | P2 | Answer-sheet extraction is synchronous across browser and chat entry points; its model work may exceed caller/admission deadlines. | Disconnect/retry ambiguity and work continuing beyond the requesting UI. | `backend/app/api/routes/assessments.py`, `backend/app/langchain/workflow_tools.py` |
| F06 | P2 | RAG mutations have no page-cache dependency entry. | Cached failed documents survive retry; polling can remain stopped. | `frontend/src/services/pageCache.ts` |
| F07 | P2 | Notification bell refreshes on mount and same-tab mutations only. | Background reminders and other-tab changes do not reach the badge promptly. | `frontend/src/components/notifications/NotificationBell.tsx` |
| F08 | P2, conditional | Memory/chat FTS bind the text-search configuration while expression indexes fix it to `simple`. | A generic PostgreSQL plan cannot use the matching expression index. | `backend/app/history_management/repositories/postgres.py`, `backend/app/chat/repositories/history_reader.py` |
| F09 | P2 | Background model consumers bypass shared interactive model admission. | Worker activity can consume the intended interactive headroom. | Assessment, evidence, summarization and profile workers/services. |
| O01 | Operational | Readiness observes dependencies without establishing queue progress. | Healthy API dependencies can coexist with unattended jobs. | `backend/app/api/routes/health.py` |
| S01 | Performance investigation | Stored voice intake validates/decodes, uploads, verifies by download, downloads for transcription and decodes again. Local models hardcode CPU. | Avoidable storage work; accelerator availability/loss has no shared policy. | Speech, embedding, reranker and local OCR adapters. |

The repository-wide audit covered implementation boundaries and selected acceptance paths. It did not prove the absence of other bugs or constitute an exhaustive production/security certification. No live LLM calls were used for this work.
