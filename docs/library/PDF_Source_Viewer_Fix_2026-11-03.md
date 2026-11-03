# PDF source visibility and upload-only notices — 2026-11-03

The reported lecture PDF was extracted, saved and embedded. A source dialog opened before publication could remain empty after ingestion finished, because it retained its opening-time source metadata. Passage-read failures also displayed an empty-extraction message. This fix distinguishes those states and refreshes the open dialog.

Baseline source: `4e49dab`. Older audit/model evidence remains unchanged. No hosted LLM calls, user-material reuploads, reindexing or deletion were performed for this fix. Private PDF contents are not committed as test fixtures or evidence.

## Trace of the reported upload

| Check | Observed result |
| --- | --- |
| Original | Private original readable through Files; 42 pages, 4,564,773 bytes. |
| PDF structure | Mixed native text and images. Four pages need whole-page OCR; this is not an entirely image-only PDF. |
| Persistence | Generation READY, ingestion SUCCEEDED, 66 saved passages, no job error. |
| Embeddings | 66 actual Qdrant vector points; exact point identities match the saved passages. Owner/generation-scoped read-only verification. |
| Provenance | 38 native-text spans, 4 full-page OCR spans, 24 embedded-image OCR spans; 51 notes retained in backend metadata. |
| Source query | The version/generation source query returns all 66 passages. Version metadata includes the published generation. |
| Recorded publication time | 34.666 seconds from generation creation; one historical operation, not a benchmark. |

[Sanitized live trace](verification/pdf-source-2026-11-03/affected-source-trace.json) records counts without source text or learner identifiers. These results rule out total extraction/save/embedding failure for this upload. Browser tests independently reproduce the stale-dialog path matching the screenshot; they do not establish the timing of the user's original click.

## PDF pipeline retained

| Stage | Existing behavior verified |
| --- | --- |
| Original and queue | Files retains the authenticated original and immutable source version; upload acceptance queues ingestion. |
| Parsing isolation | RAG materializes the original and runs the Documents reader in a killable wall/CPU/memory-limited subprocess. |
| Native PDF text | pypdf layout extraction; encrypted files and page-limit violations fail explicitly. |
| Scanned pages | Pages with fewer than 25 native characters and images, or no native text, use Poppler at 120 DPI plus English Tesseract. Required unavailable OCR tools raise an actionable error. |
| Mixed pages | Retain native text plus embedded-image OCR; duplicate image OCR is reused within the parse request. Notes preserve unreadable content. |
| Chunks and vectors | Preserve page/method/offset provenance, split within E5 token limits, save chunks, embed and upsert, verify count and exact point identities, then publish READY. No usable text fails rather than publishing an empty ready source. |
| Retrieval and viewing | Original download and extracted-passage reads are separate authenticated paths. Citations retain immutable version/generation identity. |

No OCR model, language, DPI, embedding identity/precision, reranker, chunking policy or source bytes changed. This corrects visibility/status and verifies the working scanned-PDF path; it does not claim improved OCR accuracy.

## Implemented behavior

| Fix | Outcome |
| --- | --- |
| Live viewer source | Opening before publication no longer freezes an empty result. Current version metadata triggers passage loading when ready, even while unsaved metadata edits protect the form draft. Citation viewers retain their supplied generation. |
| Version status | Add `extraction_state` (`processing`, `ready`, `failed`, `unavailable`) and `extraction_error` to version metadata. Historical failures no longer depend on the truncated recent-job/generation list. |
| Read versus extraction errors | Pending sources show reading/indexing; failed sources show the sanitized job error and retry guidance. Read errors do not also claim extraction returned no text. Indexed-but-missing passages are identified as a loading inconsistency. Refresh invalidates document caches. |
| Failed reindex | Previously published content remains readable, with an explicit indication that the latest attempt failed. Unpublished chunks remain inaccessible. |
| Query budget | All status joins use the existing batched version query; the Library listing retains its seven-query bound. |
| Upload notice | One OCR notice only while a PDF/image is selected/uploading; it disappears on acceptance. No persistent per-page warning lists on the material page or source viewer. Actionable processing/read errors remain available. |

The user's upload-only warning preference superseded the initial collapsed-notes presentation before release. Detailed notes remain stored for provenance and debugging. Intermediate browser artifacts describing notes disclosures are historical, not the final UI contract.

## Accepted evidence

| Artifact under [verification/pdf-source-2026-11-03](verification/pdf-source-2026-11-03/) | Result |
| --- | --- |
| `affected-source-trace.json` | Actual affected material: 66 saved passages and 66 matching vector points. |
| `version-baseline.txt` | Both new status/error checks fail against the original implementation. |
| `viewer-baseline.txt` | Three valid stale/pending/failure regressions fail on the original viewer. The fourth initial assertion also failed but expected HTTP error copy that the client intentionally masks; corrected thereafter. |
| `backend-acceptance.txt` | **93 tests pass** across PDF/source status, ingestion/retrieval, source APIs, parser/OCR, chunking and query-count behavior. |
| `older-version-acceptance.txt` | **1 additional test passes**, added after that combined run started: historical-version error and owner isolation. |
| `browser-acceptance.txt` | **16 tests pass**: nine source/upload-notice cases and seven existing Library cases. Includes 42 synthetic notes without permanent warnings, one upload notice disappearing on acceptance, pending-to-ready refresh, read retry, prior-content fallback and unsaved edits. |
| `cache-recovery.txt` | Final focused test confirms Refresh content replaces a cached empty response with repaired content. |
| `real-ocr-e5.json` | True image-only PDF, zero native characters -> actual isolated OCR -> saved passage -> 384-dimensional cached E5 vector -> dense-only retrieval. Original bytes and OCR provenance preserved. Isolated Qdrant local; no hosted calls. |
| `frontend-final-build.txt`, `static.txt`, `frontend-conventions.txt` | TypeScript/Vite, Ruff F/E9 and theme/UI checks pass. Existing large-bundle warning remains. Final Docker build/runtime receipts follow deployment. |

Do not sum overlapping test runs. Preserved intermediate failures: `backend-focused.txt` caught a temporary nine-query regression, fixed by batching; `backend-final.txt` had one test calling a nonexistent convenience API, corrected to repository reindex; `backend-corrections.txt` passes six focused cases. `browser-upload-only-warnings.txt` exposed a drag/drop fixture dispatching on the loading skeleton; it now waits for the real form. `viewer-fixed-first.txt` records the HTTP-copy assertion mismatch. `browser-final.txt` and `viewer-fixed.txt` precede the user's final warning policy. Accepted artifacts above supersede them.

## Reproduction and rollout

Use a disposable `TEST_DATABASE_URL` and installed/baked model assets. Recorded backend tests use PostgreSQL 17, current source mounted read-only into the cached dependency image, in-memory private-file fixtures and isolated schemas. Tests never use application `DATABASE_URL`. The image-only experiment uses actual local Poppler/Tesseract and E5, with Qdrant local for isolated vector behavior. The separate affected-file inspection reads the configured live Qdrant.

```text
python -B -m unittest tests.rag.test_pdf_source_status tests.rag.test_workflows tests.rag.test_api tests.rag.test_parsers tests.documents.test_readers tests.vision.test_ocr tests.rag.test_processing
python -B -m testing.verify_scanned_pdf_source
```

From `frontend`:

```text
npm run build
npx playwright test renovation-pdf-source.spec.ts renovation-library.spec.ts --config playwright.visual.config.ts
npm run check:theme
npm run check:ui
```

No migration or reindex is required. Rebuild backend/frontend from the implementation commit and recreate existing API/worker/frontend containers without deleting volumes. Source metadata changes are additive. Rollback uses prior code/images with no data conversion. Existing private originals, canonical chunks, vectors and old artifacts are preserved. English OCR remains imperfect for handwriting/diagrams/equations; this is not comprehensive accuracy or load certification.

Docker identities and running-service checks are recorded in the accompanying runtime receipt after source commit. Runtime verification does not imply a fresh live LLM test.
