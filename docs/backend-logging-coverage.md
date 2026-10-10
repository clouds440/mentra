# Workflow logging coverage and verification

Automatic connections cover public operations at each listed boundary. Explicit scopes handle transaction ownership, isolated parsing, provider/tool dispatch, and durable worker attempts. Logging assertions and representative generated examples complement existing domain regression tests; provider behavior is mocked and the database is isolated.

| Workflow | Connected boundaries | Regression evidence |
| --- | --- | --- |
| Authentication and external provisioning | Token/cookie dependencies, auth service, passwords, verifier, identity repository, EduVerse provisioning | `auth/test_auth.py`, `student_profile/test_eduverse.py` |
| Profile and calibration | Profile/calibration/evidence services, profile transaction/store, evaluator; explicit degraded evaluation status | `student_profile/test_profile.py`, `test_evaluator.py`, `test_observability.py` |
| Persistent/stateless chat | Conversation service/context/repository, reply/orchestration, plan, LLM, tools, history reader, isolated generation collector | `test_persistent_chat.py`, `test_chat_endpoint.py`, `test_orchestration.py`, `test_streaming.py` |
| Conversations and SSE | ASGI lifecycle, public repository operations, SSE close/disconnect; no token/heartbeat payload logging | `test_persistent_chat.py`, `test_observability.py` raw ASGI lifecycle scenarios |
| Material ingestion/deletion/reindex | RAG service/repository, storage, parser, chunker, embeddings, Qdrant, worker claim/stages/publish/fail/retry and reconciliation | `rag/test_workflows.py`, `rag/test_api.py`, vector/index tests |
| Retrieval and source access | Scope/eligibility through service/repository, embedding/vector adapters, reranker with context-copy executor, source hydration, approved result counts | RAG workflow/API/reranker suites |
| Documents/attachments/OCR | Attachment service/repository, documents facade/detection/isolation/readers, vision adapters; parser stdout remains its result protocol | `documents/test_readers.py`, `vision/test_ocr.py`, orchestration and parser tests |
| Learner | Engine, concepts/context/evidence/state/retrieval services, inherited PostgreSQL stores, owned and borrowed transaction managers | Learner engine/integration/persistence/realistic-learning suites |
| History/memory | History service, validator, memory repository, lookup/read facade, tools, maintenance CLI | `test_history_management.py`, orchestration/history tool suites |
| Events/proposals | Event/proposal services/repositories, graph review/checkpoint scopes, notification publication, reminder producer | `test_events.py`, `test_events_api.py`, `test_event_proposals.py` |
| Notifications/reminders | Inbox/preferences/sync repository/service, owner transactions, batch workflow; empty batches quiet, due batches visible | `test_notifications.py`, reminder concurrency/retry/dedup tests in Events suite |
| Assessments/evidence jobs | Generation/submission/extraction service, grading/evidence workflows and worker collectors, repositories and durable origin envelopes | `test_assessments.py`, `test_chat_evidence_jobs.py`, `test_observability.py` durable correlation |
| Lifecycle/migration | API startup collector, service factories, readiness/init, migration CLI and process shutdown, independent worker configuration | `test_observability.py` actual app lifespan fixture, migration concurrency/drift/downgrade suites |

The additive logging migration is rehearsed against legacy records. Existing historical-schema snapshot checks explicitly omit columns introduced after the revision being compared; latest-schema drift checks still compare the entire metadata.

New modules outside this list work through `connect_module()` without editing this document or any runtime registry. This inventory records current implementation coverage; it does not act as a logging allowlist.

Generated examples and the local benchmark are in [logging examples](logging-examples/). The benchmark compares the same bounded nested mock workflow with a no-op sink and JSON formatting to memory. It excludes real terminal backpressure, DB/provider latency and external services. The implementation keeps synchronous output; it does not claim bounded latency from a slow terminal.

Application deployment and application database migration are separate from isolated verification. The source requires schema revision `20261010_0014` before startup.
