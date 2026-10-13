# Automatic capture from chat

Temporal/first-party activity hints trigger bounded semantic extraction before
the answering agent runs. Subjects and event categories are not an allowlist:
an arbitrary activity with a first-party temporal statement can be captured.
The extractor returns exact current-message quotes, event candidates, admission
decisions and a separate explicit-practice intent. It never reads documents,
assistant text or summaries as new event evidence.

The existing EventProposalService admission/commit pipeline remains the writer.
Unambiguous complete actual events can be committed automatically; uncertain
dates/timezones remain pending proposals. Account automatic_events preferences
remain authoritative. Calendar categories not represented by the current schema
use other with a descriptive title, including projects and presentations.

An account timezone overrides the validated browser timezone stored on the
original user message. Retries retain that original timezone and occurrence
timestamp. Existing message proposals are replayed without another extraction
call or duplicate write. Capture is limited to three candidates and 25 seconds;
failures reach the agent without deterministic UI warning boxes. Partial success
keeps the successful receipts so the agent can acknowledge actual saves.

The answer receives canonical saved events/proposals. A scheduled-event
announcement does not preselect assessment_generate. If extraction confirms
the user did not ask for practice, generation is rejected before side effects;
the agent can offer preparation advice and ask whether practice is wanted.
Explicit practice requests still use normal tool discovery and assessment flow.
