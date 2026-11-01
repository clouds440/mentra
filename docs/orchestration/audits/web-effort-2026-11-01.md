# Search effort review: Ottoman history response

Reviewed the saved user question, full persisted answer, source metadata and complete
foreground trace `31885fa9bf3541b198bfd42cc21d4f97` on 2026-11-01.
No historical chat content or outcome was changed.

## Recorded request and execution

The request asked for a detailed Ottoman history covering rise, rulers, events, culture,
politics and decline, with historical images **if available**. It warranted a substantial
educational answer, but did not ask for an exhaustive research report or particular images.

| Metric | Recorded value |
| --- | --- |
| Foreground generation | 117.05 seconds |
| Normal search dispatches | 9 |
| Registered sources | 24 (not 24 search calls) |
| Research dispatches | 0; authenticated research was configured |
| Main model calls | 7 |
| Input tokens | 130,600 total; 37,120 cached, 93,480 uncached |
| Output tokens | 3,669 |
| Persisted image URLs | 23 across sources; 4 embedded in the answer |
| Outcome | Completed |

| Model round | UTC start | Searches selected before the next round |
| --- | --- | --- |
| 1 | 10:22:02 | 2 |
| 2 | 10:22:17 | 2 |
| 3 | 10:22:32 | 2 |
| 4 | 10:22:48 | 1 |
| 5 | 10:23:00 | 1 |
| 6 | 10:23:12 | 1 |
| 7 | 10:23:28 | Final answer; model completed at 10:23:49 |

The source inventory shifted from broad history and a portrait to Vienna imagery,
Suleiman portraits and maps. Image resolution ran on all nine searches, repeatedly
paying page/image validation time. Several hosts failed locally, and the optional
image-index phase timed out repeatedly; successful checked assets were still available.
The final answer even listed unrequested missing illustration subjects as a limitation.

## Assessment

Editorial rating: **6/10 usefulness; 3/10 resource efficiency**. These are judgments of
coverage and presentation, not an independent historical fact-check. The chronology,
headings, timeline diagram and four images are useful. Portrait-attribution details
receive disproportionate attention, the final collapse is compressed, and sweeping
stagnation/adaptation claims are presented with insufficient historiographic nuance.
Nine searches and seven repeated context submissions did not produce commensurate value.

## Causes and changes

| Cause | Change |
| --- | --- |
| Flexible headroom lacked an adequate semantic stopping policy | Main model chooses direct answer, quick lookup or deep investigation within the existing invocation; allowances are ceilings, not goals |
| Self-selected illustration subjects became gaps | Optional pictures have no minimum count; use relevant checked assets already found |
| Repeated rounds lacked a compact evidence inventory | Runtime includes search/research counts, admitted sources/images, last-batch novelty and remaining research dispatch |
| Further queries lacked an explicit purpose | Optional `evidence_gap` argument asks for a material missing fact, conflict or actually required asset; no new rejection fence |
| Long ordinary search chains substituted for research | Tool descriptions, capability catalog and centralized prompts distinguish detailed overviews from investigations and direct deep work to available `web_research` |
| Packet compaction dropped later assets too early | Reclaim excerpt verbosity across all sources before dropping sources; existing packet limits stay fixed |
| A spent research tool still appeared callable | Retire its bound schema after the existing one-dispatch allowance is used |

No extra routing/model invocation, keyword classifier, lower search cap, schema migration
or frontend change is introduced. Real gaps can still use the existing adaptive allowances.

## Verification

- 110 affected backend regressions passed against disposable PostgreSQL, including packet
  limits/immutability, later-asset preservation, distinct failure/outcome handling, recovery,
  inventory propagation, duplicate query caching and spent research-schema retirement.
- Configured-model replay of the original question completed with 2 search calls and
  3 model rounds, using 25,157 input / 1,997 output tokens and embedding images.
- Direct stable explanation used 0 searches and 1 model round.
- Deep investigation selected discovery then 1 research call and finalization, with no
  normal searches or research retry. Its deliberately incomplete research fixture correctly
  produced a partial answer rather than pretending the missing scholarly evidence existed.
- An empty-search fixture allowed further ordinary lookups and completed in 3 searches;
  guidance did not prevent recovery or become a two-call hard limit.

These replay checks use real configured model calls and saved public evidence with synthetic
search/research transports. They do **not** establish production search latency or factual
research quality, and model decisions can vary. The original trace metrics above are live
production evidence; the replay is a bounded behavioral regression check.
