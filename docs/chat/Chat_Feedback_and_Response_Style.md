# Chat feedback and response style

Implemented 14 October 2026.

## Flicker trace and fix

The store previously published `busy` before appending the optimistic question,
mounting activity under the preceding exchange. The activity then moved to the new
exchange. A second remount happened when its React key changed from the previous
turn to the acknowledged turn. Both restarted the logo and reset feedback.

Send now publishes the optimistic exchange and busy state atomically. Activity has
stable component identity across acknowledgement. A late status poll for the
preceding turn cannot retire the pending exchange. A browser DOM-identity probe
verifies that the same activity row and logo remain connected through the handoff.

## Feedback rules

- Sending: “Sending your message”; acknowledged default: “Thinking”.
- Labels come from a closed client vocabulary, never raw server/model messages.
- Meaningful steps include searching/reading sources, reviewing web results,
  connecting relevant details, preparing questions, adapting to learning progress,
  preparing feedback, reviewing events and preparing options.
- Response assembly says “Putting it together”. Raw streamed answer text remains
  hidden until the canonical formatted message is ready.
- Completed actions have contextual follow-through labels. Routine profile/setup
  reads and unknown operations retain the previous meaningful label.
- Updates have a 650ms minimum display interval; bursts coalesce to the latest
  meaningful state. This never delays canonical answers or their reveal.
- Retry, limited information, unconfirmed changes and required input retain safe,
  accurate wording. Stop immediately says “Stopping this response”.
- After 12 seconds without new meaningful activity, ordinary processing can say
  “Still working on your request”; there is no invented carousel of work stages.
- Duplicate text/token events advance the reconnect cursor without rerendering
  activity or storing answer tokens in React state. Reconnect retains feedback.

## Learning preference trace and fix

The current profile was already fetched for ordinary and tool-assisted chat, but
its preference enum was only supplied as data. The base prompt encouraged teaching
without explicitly translating those preferences into scope and length.

`langchain/response_style.py` now translates only known preference/depth enums into
server-owned guidance. `ChatService` includes it in context for stateless chat,
first-turn structured answers, subsequent turns and all tool/fallback rounds.
The versioned chat prompt is now `chat-v11`.

Concise means answer first, ordinarily below 100 words, one short paragraph or a
few short bullets, and stop once answered. Unrequested lessons, extra examples,
recaps and follow-up offers are omitted. Deep explanation settings do not override
concise unless the current request asks for elaboration. Other preferences guide
examples, steps or concepts when relevant to the current request. Explicit scope,
format, question counts and complete requested artifacts take precedence.

This uses prompt guidance rather than truncation or a low global output cap that
could break code, structured responses or domain-tool arguments. It is a model
instruction, not a deterministic word-count guarantee. Profile free text is never
converted into trusted instructions, and no preference data is cached across turns.

## Evidence

- 34 backend regression tests passed with an isolated disposable PostgreSQL database.
- 22 focused browser tests passed for feedback, recovery, caching, responsive scroll,
  Markdown reveal, deletion and new-chat handling. The extended Stop/DOM continuity
  test also passed against current development source and the updated production
  container. Theme and UI checks passed.
- Model request inspection verifies latest settings, every preference/depth, first
  structured turn and tool/final rounds. Requested output is never sliced.
- One live anonymous provider comparison for “Explain how photosynthesis works.”
  returned 136 words with balanced and 55 with concise, both at standard depth.
  This is a smoke check, not a general model-quality benchmark.
- Production backend/frontend Docker builds and serving checks passed; local
  containers were updated. No data migration was needed.
