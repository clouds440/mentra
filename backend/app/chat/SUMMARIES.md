# Conversation context compaction

Original user-facing messages remain unchanged. `chat_summary` stores private
content, a completed-message sequence watermark and a revision against the
owner/chat ID. Every persistent request loads the latest summary. Older retried
turns cannot see a summary covering future messages.

Normal answering requests admit 8,192 input tokens, with a bounded 12,288-token
allowance for large questions, images, recovering unsummarized history and needed
tool schemas. Output remains separately bounded at 2,048 tokens. Assessment
generation/grading retain their existing 16k workflow context. Budget events and
provider usage events include answering and `chat_summary` calls separately.

Recent verbatim history targets 1,800 tokens. Up to 4,096 tokens of unsummarized
history can be retained while compaction catches up or fails, within the total
input cap. Completed historical exchanges displaced from the recent suffix are
summarized incrementally after a response, once approximately 2,000 tokens have
accumulated. Each job admits at most 5k tokens of new messages and 600 output
tokens. Large individual messages use marked excerpts and original ID references.
Only complete exchanges advance coverage; bounded batches never skip gaps.
The recent suffix is computed from the actual newest messages before loading
the oldest bounded backlog page, so long chats of short messages can progress.
Provider output cut off by the output limit is rejected without advancing coverage.
Batch admission counts each new record once and verifies the assembled packet,
avoiding repeated tokenization of a growing payload. Threshold checks stop at
the threshold; pending leases/cooldowns skip backlog reads and tokenization.

A database lease prevents parallel paid calls across processes/devices. Lease
tokens and summary revisions fence publication. Failed jobs retain the last
summary, do not fail chat answers, perform no paid retries and cool down for an
hour. A crash leaves a two-minute lease; a later completed turn can resume work.
There is no autonomous drain loop or eager paid backfill on opening old chats.
Deletion removes summary content and fences in-flight publication.
An optional summary-read outage falls back to original history without failing
the answer; ownership/deletion failures remain authoritative. A response fenced
out by Stop or deletion never schedules compaction.

Summaries are historical background, organized by topic with resolved/superseded
state. Chat instructions prioritize the current request/corrections and prohibit
unrelated recaps, old upload caveats and reopening resolved topics. Summaries
never populate visible/evidence IDs. `history_lookup` retains lexical search and
adds owner-bound exact message retrieval with a token-bounded continuation offset
for original code or evidence. Content offsets require exact current-chat IDs;
future and deleted messages cannot be recovered.
Matching messages are prioritized over neighboring context in model packets;
partial deliveries remain eligible for recovery. Tool-schema admission updates
both token and byte allowances for results within the selected total input limit.

`CHAT_SUMMARY_ENABLED=false` disables summary calls and injection as a rollback.
Changing chat input settings does not change assessment limits.
