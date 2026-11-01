# Follow-up: enforce quick lookup and correct optional-only failures

The earlier prompt-focused patch was deployed, but did not prevent a real follow-up
from repeatedly searching variants of one missing detail. The original replay's
constant evidence set did not reproduce a provider returning new URLs on every query.

## Actual failing turn

Trace `e5706a311cf74240830d4e94b8aefaf8`; prompt: “What about Taimor Lung and how he
defeated Ottoman”. Backend revision `e3178c9` was running and healthy.

| Measurement | Recorded value |
| --- | --- |
| Normal search calls | 12 (last call hit quota) |
| Registered sources | 33 |
| Main model rounds | 11 |
| Input tokens | 214,812 (66,304 cached) |
| Output tokens | 3,839 |
| First model round to final usage event | About 110 seconds |

The retained checkpoint shows repeated queries for water diversion, a feigned retreat,
Anatolian defections and the Ottoman left flank. Changes in wording and website scopes
avoided exact-query deduplication. New sources counted as progress despite the repeated
evidence gap. The final answer declared its explanation complete and its missing battle
images optional, but still declared the entire response partial.

## Changes

- Normal search has an enforced quick phase of two lookup calls. Empty initial batches
  can recover automatically up to four; in-flight requests cannot inflate the allowance.
  Spent normal-search schemas retire from model bindings, and dispatch also enforces the
  phase for an oversized or invalid provider-emitted batch. Result reservations count
  admitted siblings so declined extras cannot starve useful evidence packets.
- Deeper investigation remains available through existing tool discovery. Explicit
  `web_effort={reason:...}` chooses research when configured, or flexible extended normal
  search when research is absent. Re-enabling a spent normal lookup does not reset it.
  There is no added classification model invocation or globally lowered workflow ceiling.
- Quota/rate-limit receipts close further normal dispatches for the turn.
- Completed required tasks plus only explicitly optional failures resolve to completed.
  Required failures, uncertain writes and provider-truncated replies remain incomplete.
  Required receipt references take precedence over overlapping optional references.
- Read projections correct the same explicit contradiction in saved outcomes without
  changing stored text, receipts or history. Both turn and message projections agree.
- Response outcome feedback appears once inside its message. The duplicate composer
  banner is suppressed when the matching inline notice is visible; input/send errors
  and failures without a visible response retain feedback.
- Mermaid uses a shared Mentra theme in light and dark: softly rounded boxes, subdued
  palette borders, bundled chat typography, no glow, and portable embedded SVG styles.
  Explicit model colors, shape meanings, sanitization and deferred loading remain intact.

## Verification and limits

- 152 backend checks passed with dedicated disposable PostgreSQL. Coverage includes
  always-novel results, oversized batches, deliberate escalation, provider quota,
  required/optional collisions, saved-outcome projections and persistent recovery.
- The actual saved final decision was checked entirely locally: partial became completed,
  retryable became false, with zero database writes or external model calls.
- The configured-model authored follow-up fixture used one normal lookup and two model
  rounds, completed in 6.24 seconds with 14,646 input / 346 output tokens. Search is a
  fixture, so this is not a production web-latency benchmark. A synthetic deep-routing
  check chose one research call; its intentionally insufficient report remained partial.
- 51 frontend checks passed: 45 rich/diagram checks plus five outcome-feedback checks
  and the existing 200-message no-rerender/typing check. Diagram families, custom colors,
  label visibility, light/dark, responsive/fullscreen and SVG/PNG exports were covered.
- Automatic approval review rejected sending the retained conversation to the configured
  external model for replay because it could contain private content. That replay was not
  performed; local saved-decision validation and authored synthetic model checks were used.

These changes enforce normal lookup effort, not a promise that every model/provider call
finishes instantly or that evidence always supports a complete sourced answer.
