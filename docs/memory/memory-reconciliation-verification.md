# Memory reconciliation verification — 2026-10-29

The release adds stable-ID automatic updates, evidence-preserving history and restore. It does not bulk merge historical records. See [behavior and limits](history-management.md#background-reconciliation).

| Check | Observed result |
| --- | --- |
| Isolated PostgreSQL regressions | 138 passed across history management, memory reconciliation, memory summaries, semantic orchestration and chat summaries; three independently reproduced baseline failures excluded |
| New reconciliation regressions | 17 passed: stable identity, enrichment, reaffirmation, independent facts, manual protection, pinning, chronology, reversals, forgetting, ownership, stale candidates, atomic rollback, opt-out, sensitive/inferred updates, restore, worker capture, foreground revision/replay, support bounds, semantic backfill/outage, deleted sources and leases |
| Browser checks | 3 passed: revision restore with refreshed evidence, existing settings CRUD/draft retention, opt-out/mobile settings |
| Frontend | Production build, theme checks and UI checks passed |
| Python static checks | Targeted Ruff `F,E9` checks passed; new modules formatted; Git whitespace check passed |
| Configured LLM, synthetic examples only | Replacement, additional concurrent fact, enrichment, Arabic replacement, uncertainty and explicit manual correction passed structured schema and domain-admission checks; one combined capture call per message |
| Local embedding runtime | Deployed `intfloat/multilingual-e5-small`, 384 dimensions: Arabic phone change ranked the English phone fact above unrelated music/math examples |
| Migration rehearsal | Private application-schema backup restored into disposable PostgreSQL 17; upgrade to `20261029_0038` preserved all selected record counts |

The migration rehearsal preserved 9 memories, 9 evidence records, 11 memory revisions, 116 chat messages, 8 assessments, 13 attempts and 46 concepts. Only the 9 current memory revisions received snapshots; unavailable historical content was not invented. A private pre-deployment dump is retained under ignored `.cache/backups/`.

The following failures reproduce on unchanged `f95ccec`, with identical failure categories, and were not counted as passing:

- `HistoryManagementTests.test_tool_limits_unknown_calls_and_provider_fallback`: the legacy `NoTools` fake lacks `bind_tools`.
- `HistoryManagementTests.test_real_tool_loop_remembers_and_retrieves`: legacy tool-loop fake does not produce the expected saved memory.
- `MigrationRehearsal.test_additive_upgrade_downgrade_preserves_chat`: existing migration `0036` intentionally refuses a destructive downgrade of recovery data.

Verification is local acceptance evidence, not a claim that the entire repository suite or a public deployment was tested. Model interpretation and bounded semantic retrieval can still miss a paraphrase; ambiguous conflicts and independently saved matching records remain reviewable rather than silently merged. Semantic outages defer background capture for larger memory collections. Roll application code forward or restore a tested backup; the migration refuses to discard saved revision content through downgrade.
