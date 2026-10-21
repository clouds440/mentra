# Chat tool-discovery and provider-protocol incident

21 October 2026. Investigation of the assistant reply containing raw DSML tool markup.

## Evidence

The affected turn is trace `e89e5ab0dcf941d49047145a0e9d0e20` in `logs/backend/backend-2026-10-21.log`, at approximately 23:21 Asia/Karachi (18:21 UTC).

| UTC time | Observed event |
|---|---|
| 18:21:42 | Profile and memory-summary preparation succeeded |
| 18:21:43.206 | First model round: 4 tools, 661 schema tokens, 8,192-token input allowance, not final |
| 18:21:44.744 | `enable_workflow_tools` succeeded and enabled two history tools |
| 18:21:44.746 | Second model round immediately became final, with **zero tools** |
| 18:21:45.579 | Provider returned 217 characters as ordinary answer text, with zero parsed tool calls |
| 18:21:47.155 | The malformed answer was stored as an assistant message |

No `conversation_summary_search` or `history_lookup` execution appears in that turn. The database reply contains the provider's `<｜｜DSML｜｜ calls>` and `invoke` markers. A separate read-only verification found all nine saved conversation summaries present and valid.

## Failure chain

Tool discovery checked that the larger instructions and tool schemas fit, but did not require a minimum remaining allowance for a real lookup result. It could approve enabling a tool and reduce the result budget below the coordinator's stop threshold. The next round then removed the tools immediately. The original logs record the final-round flag but not its specific stop reason; code review and a synthetic large-context reproduction identified this budget gap. New logs record the individual stop reasons and remaining result space.

With tools removed, the provider emitted its native tool-control syntax as plain content rather than a structured function call. Streaming forwarded that content, and the coordinator accepted the no-tool-call response as a final answer. The new summary tool exposed this existing discovery-budget and output-validation gap. The earlier regression tests used valid structured tool calls and did not cover this combined path.

## Corrections

- Discovery now reserves room for its receipt and a real lookup result. When necessary it uses the existing configured 12,288-token recovery allowance; it rejects schemas that cannot leave enough result space.
- Bare provider tool-control markup is rejected as an answer. An incomplete leading tag is buffered across stream chunks so split control markers cannot leak into the public preview.
- The coordinator can request one correction using native function calls. Raw text is never parsed or executed as a tool request. A repeated malformed response fails with a normal public error instead of being saved as a successful answer.
- Model-round logs now include final-round reasons and remaining result tokens/bytes, without logging private content.

The original malformed stored message is preserved for diagnosis. No conversation, memory, assessment or summary record was deleted or rewritten by this fix.

## Verification

- 148 backend tests passed, including discovery with constrained result space, split streamed protocol tokens, nonstreamed malformed output, one successful native repair and bounded failure on repeated malformed output.
- A live call through the configured provider used only synthetic context and fake read-only tools. It successfully executed summary search followed by history lookup with the recovery input allowance and produced no raw protocol output or preview.
- The live probe sent no real user history and wrote no database records.
