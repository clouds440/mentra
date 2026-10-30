# Mentra documentation

Documentation is grouped by the module or shared concern it describes. Each folder keeps its related plans, current contracts, screenshots and recorded evidence together.

**Read current contracts for behavior.** Plans express intent; dated reports and screenshots describe their recorded run. Neither establishes the current deployed state.

| Module / concern | What lives here |
| --- | --- |
| [Getting started](getting-started/README.md) | Local setup, prerequisites and configuration. |
| [Architecture](architecture/README.md) | Backend atlas, module boundaries and architecture audits. |
| [Chat and interactive learning](chat/README.md) | Durable conversations, rich responses, questionnaires, saved search and UI interactions. |
| [Assessments](assessments/README.md) | Practice, papers, answer sheets, grading, mistake/revision practice and recovery. |
| [Learning Progress and Learner Engine](learning/README.md) | Topics/subskills, evidence, mastery policies, recommendations and learner verification. |
| [Profile and teaching preferences](profile/README.md) | Onboarding, calibration, user-owned teaching context and preference contracts. |
| [Identity](identity/README.md) | Local authentication, sessions, account behavior and browser identity. |
| [Library and retrieval](library/README.md) | Source ingestion, provenance, E5 retrieval, reranking and verification. |
| [Documents](documents/README.md) | Current document reading/extraction and the explicitly planned document-writing capability. |
| [Vision](vision/README.md) | OCR, image preparation, rasterization and reviewed transcription. |
| [Speech](speech/README.md) | Local multilingual voice input and transcription. |
| [Events](events/README.md) | Agenda, temporal semantics, proposals, calendar exports and reminders. |
| [Notifications](notifications/README.md) | Independent inbox, preferences, synchronization and reminder delivery. |
| [Memory and history](memory/README.md) | Exact history recovery, admitted memories, supported summaries and reconciliation. |
| [Web search and research](web-search/README.md) | Current-knowledge providers, quotas, dated sources and citation contracts. |
| [Private files](files/README.md) | Unified private-original storage, bindings, delivery and migration design. |
| [AI orchestration](orchestration/README.md) | Model/tool coordination, discovery, prompt/caching policy and workflow optimizations. |
| [Observability](observability/README.md) | Correlated content-free logging, coverage and recorded examples. |
| [Database](database/README.md) | Query audits, optimization plans and implementation evidence. |
| [Frontend and design system](frontend/README.md) | Layout, themes, loading, accessibility and frontend renovation plans/reports. |
| [Deployment and recovery](deployment/README.md) | Production configuration, migration/preservation constraints and dated release evidence. |
| [Product and showcase](product/README.md) | Product recommendations and reproducible product-showcase captures. |

## Start here

- [Setup](getting-started/SETUP.md)
- [Backend atlas](architecture/Mentra_Backend_Map.md)
- [Production runbook](deployment/production-readiness.md)
- [Product showcase](../README.md)
- [Document writing roadmap](documents/Document_Writing_Plan.md)

## Organization rules

Keep new material in its owning module folder. Use `screenshots/showcase/` for current product captures, `screenshots/history/` for preserved earlier images, and `verification/` or `audits/` for dated evidence. Cross-cutting orchestration, database, frontend and deployment material has its own folder. Source-local READMEs remain beside their implementation.
