# Mentra RAG System --- Full Implementation Plan

**Status:** Architecture plan aligned to current RAG foundations; ingestion and retrieval workflow phases remain planned.
**Audience:** Human developers and AI coding agents\
**Scope:** Document ingestion, parsing/OCR, chunking, indexing,
retrieval, reranking, provenance, context lifecycle, embedding
training/evaluation, and public integration contracts.

------------------------------------------------------------------------

# 1. Objective

Implement Mentra's RAG subsystem as an independent knowledge-retrieval
module.

Current RAG foundations are already present in `backend/app/rag/`: a local embedding service, vector-store protocol, Qdrant adapter, and learner-scope contract. The plan below completes ingestion/retrieval by extending those modules and adding domain services/repositories where needed; it must not create parallel embedding or Qdrant clients.

RAG owns:

-   uploaded learning-material metadata;
-   parsing and text extraction;
-   OCR routing for scanned/image material;
-   document structure preservation;
-   cleaning/normalization;
-   semantic/structure-aware chunking;
-   chunk metadata and provenance;
-   embedding generation;
-   vector indexing;
-   sparse/BM25 indexing where used;
-   context-aware retrieval;
-   hybrid fusion;
-   reranking;
-   citation/source metadata;
-   document lifecycle;
-   retrieval evaluation;
-   embedding fine-tuning/evaluation where justified.

RAG does **not** own:

-   learner mastery;
-   learner evidence;
-   learning recommendations;
-   LLM orchestration;
-   canonical assessment state;
-   conversational memory.

Core rule:

> **RAG answers "what source material is relevant?" The Learner Engine
> answers "what does this student know?" LangChain/LangGraph decides
> when and how to combine them.**

------------------------------------------------------------------------

# 2. Architectural Boundary

``` text
                         LangChain / LangGraph
                                â”‚
                 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                 â–¼                             â–¼
          Learner Engine                   RAG Engine
                 â”‚                             â”‚
       active contexts / concepts              â”‚
                 â”‚                             â–¼
                 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–º retrieval filters
                                               â”‚
                                               â–¼
                              ranked chunks + provenance
```

RAG may receive:

``` text
query
learning_context_ids
concept_ids
document_ids
retrieval mode
limit
```

RAG returns relevant source material.

RAG must not query learner mastery tables directly.

------------------------------------------------------------------------

# 3. Recommended Module Structure

Adapt to repository conventions while preserving boundaries.

``` text
backend/app/rag/
â”œâ”€â”€ __init__.py
â”œâ”€â”€ schemas/
â”‚   â”œâ”€â”€ documents.py
â”‚   â”œâ”€â”€ chunks.py
â”‚   â”œâ”€â”€ retrieval.py
â”‚   â””â”€â”€ ingestion.py
â”œâ”€â”€ services/
â”‚   â”œâ”€â”€ rag_service.py
â”‚   â”œâ”€â”€ ingestion_service.py
â”‚   â”œâ”€â”€ retrieval_service.py
â”‚   â””â”€â”€ source_service.py
â”œâ”€â”€ parsers/
â”‚   â”œâ”€â”€ router.py
â”‚   â”œâ”€â”€ pdf.py
â”‚   â”œâ”€â”€ docx.py
â”‚   â”œâ”€â”€ pptx.py
â”‚   â”œâ”€â”€ text.py
â”‚   â””â”€â”€ image.py
â”œâ”€â”€ ocr/
â”‚   â”œâ”€â”€ service.py
â”‚   â””â”€â”€ confidence.py
â”œâ”€â”€ processing/
â”‚   â”œâ”€â”€ cleaner.py
├── embeddings.py              # Existing EmbeddingService + local BGE implementation
├── vector_store.py             # Existing VectorStore protocol
├── qdrant_store.py             # Existing QdrantVectorStore adapter
â”‚   â”œâ”€â”€ fusion.py
â”‚   â”œâ”€â”€ filters.py
â”‚   â””â”€â”€ reranker.py
â”œâ”€â”€ evaluation/
â”‚   â”œâ”€â”€ datasets.py
â”‚   â”œâ”€â”€ metrics.py
â”‚   â””â”€â”€ runner.py
â”œâ”€â”€ repositories/
â”œâ”€â”€ exceptions.py
â””â”€â”€ tests/
```

Do not create unused implementations merely to match this tree.

------------------------------------------------------------------------

# Phase 0 --- Public Contracts and Skeleton

## Goal

Create a framework-independent RAG service surface before implementing a
specific vector database.

The existing foundation already includes `app/rag/embeddings.py`, `app/rag/vector_store.py`, `app/rag/qdrant_store.py`, and `app/rag/learner_scope.py`. Complete this phase by extending those contracts and adding document/retrieval services; do not create duplicate embedding or vector-store clients. Ingestion, durable document metadata, chunk indexing, and search are not implemented yet.

Primary facade:

``` python
class RAGService:
    async def ingest_document(...)
    async def search(...)
    async def get_source(...)
    async def get_document(...)
    async def update_document_context(...)
    async def archive_document(...)
    async def delete_document(...)
```

LangChain should call this service.

It should not construct Qdrant queries itself.

## Acceptance criteria

-   callers depend on RAG schemas/services rather than Qdrant;
-   parsers can be tested independently;
-   embedding provider can be replaced;
-   vector-store implementation can be replaced.

------------------------------------------------------------------------

# Phase 1 --- Document Persistence and Metadata

## Goal

Store document identity and lifecycle separately from vector chunks.

### `document`

Suggested fields:

``` text
id
learner_id (internal UUID; owner scope)
title
original_filename
media_type
file_hash
storage_path/reference
learning_context_id
status
ingestion_status
parser_version
ocr_used
created_at
updated_at
last_used_at
indexed_at
metadata_json
```

Document lifecycle:

``` text
ACTIVE
RELATED
DORMANT
ARCHIVED
```

Ingestion state should be separate:

``` text
PENDING
PROCESSING
READY
FAILED
REINDEXING
```

### `document_chunk`

Suggested metadata:

``` text
id
document_id
chunk_index
content
content_hash
page_number / slide_number / section
heading_path
learning_context_id
concept_ids
token_count
embedding_version
created_at
metadata_json
```

Do not rely on the vector database as the only source of document
metadata.

------------------------------------------------------------------------

# Phase 2 --- Upload and Ingestion Pipeline

## Goal

Create one deterministic ingestion pipeline for all supported study
material.

Supported initial formats:

``` text
PDF
DOC/DOCX
PPT/PPTX
TXT
images/scanned notes
```

Pipeline:

``` text
upload
  â†“
validate
  â†“
fingerprint/hash
  â†“
persist document record
  â†“
detect format
  â†“
parse / OCR
  â†“
normalize structure
  â†“
clean text
  â†“
chunk
  â†“
enrich metadata
  â†“
embed
  â†“
index dense
  â†“
index sparse if enabled
  â†“
mark READY
```

Ingestion must be restartable/idempotent where practical.

------------------------------------------------------------------------

# Phase 3 --- Validation and Deduplication

Validate:

``` text
supported type
size limits
non-empty content
safe filename handling
parser compatibility
```

Use content hash/fingerprint to detect identical uploads.

Do not automatically assume same filename = same document.

Deduplication policy should distinguish:

``` text
exact duplicate
new version
different file with same name
```

Do not silently discard without returning the result to the caller.

------------------------------------------------------------------------

# Phase 4 --- Parsing

## Goal

Preserve useful document structure instead of flattening everything
immediately.

Extract where available:

``` text
title
headings
paragraphs
lists
tables
page/slide boundaries
captions
code blocks
formulas as supported
```

A document parser such as Docling may be used where it improves
multi-format structural extraction.

The parser implementation must remain behind Mentra's parser interface.

## Output contract

Parsers should produce a normalized intermediate representation rather
than final chunks.

Conceptually:

``` python
ParsedDocument(
    blocks=[
        ParsedBlock(
            type="paragraph",
            text="...",
            page=4,
            heading_path=["Normalization", "Third Normal Form"]
        )
    ]
)
```

This allows chunking strategy to evolve independently.

------------------------------------------------------------------------

# Phase 5 --- OCR Routing

## Goal

Use OCR only where extraction requires it.

Examples:

``` text
digital PDF â†’ native extraction first
scanned PDF â†’ OCR
image notes â†’ OCR
mixed PDF â†’ native text + OCR only for image/scanned regions where needed
```

Do not OCR every document blindly.

Store:

``` text
ocr_used
ocr_model/version
OCR confidence where available
```

For study-material ingestion, low OCR confidence may still permit
indexing with warning/metadata depending on policy.

This is different from handwritten **assessment evidence**, where low
confidence must block learner-state mutation.

------------------------------------------------------------------------

# Phase 6 --- Text Cleaning and Normalization

Cleaning may include:

``` text
remove repeated headers/footers
normalize whitespace
repair obvious extraction artifacts
preserve meaningful punctuation
preserve section hierarchy
preserve code formatting where possible
preserve table meaning
```

Do not aggressively rewrite educational content.

Original source location must remain recoverable.

------------------------------------------------------------------------

# Phase 7 --- Chunking

## Goal

Create retrieval units based on semantic/document structure rather than
arbitrary fixed slices alone.

Preferred strategy:

``` text
document structure
      â†“
section-aware segmentation
      â†“
semantic chunk boundaries
      â†“
size constraints
      â†“
small overlap where useful
```

Avoid:

``` text
every 500 characters regardless of meaning
```

Chunk metadata must preserve:

``` text
document ID
page/slide
section/headings
chunk order
learning context
concept IDs where available
```

## Chunk size

Do not freeze one universal size before evaluation.

Evaluate candidate configurations.

Different material may need different strategies:

``` text
prose
slides
code
tables
short notes
```

------------------------------------------------------------------------

# Phase 8 --- Concept Tagging

## Goal

Associate chunks with canonical Mentra concepts where useful.

RAG must not invent durable concept IDs.

Flow:

``` text
chunk
  â†“
candidate concept extraction
  â†“
Learner/Concept Service resolve_concept()
  â†“
canonical concept IDs
  â†“
store as chunk metadata
```

Concept tagging may be deferred/asynchronous if ingestion latency
becomes excessive.

Unresolved labels must not create arbitrary canonical IDs.

Concept tags supplement semantic retrieval; they do not replace
embeddings.

------------------------------------------------------------------------

# Phase 9 --- Embedding Abstraction

## Goal

Prevent retrieval architecture from depending permanently on one
embedding model.

Reuse the implemented interface in `backend/app/rag/embeddings.py` rather than defining a competing provider API:

``` python
class EmbeddingService(Protocol):
    dimension: int
    model_name: str
    model_version: str
    def embed_query(text: str) -> list[float]: ...
    def embed_documents(texts: list[str]) -> list[list[float]]: ...
```

`SentenceTransformerEmbeddingService` already loads the locally baked `BAAI/bge-small-en-v1.5` model, adds its retrieval query instruction, returns normalized vectors, and exposes the model identity/dimension. It is initialized once at application startup and injected into `QdrantVectorStore`. Use this same service for document and query vectors in future ingestion/retrieval. Its synchronous encoding must not block an async request loop; run bulk ingestion in a worker/background job and use an appropriate thread boundary for request-time query encoding.

Store the service's embedding model/version/dimension in index metadata and document/chunk records where reproducibility requires it. Any model or resolved revision change requires an explicit reindex/migration plan.

Current configured model:

``` text
BAAI/bge-small-en-v1.5 (local, image-baked)
```

Evaluate any replacement (including BGE-M3 or a tuned model) against this baseline before adopting it.

Do not make model name part of business logic.

------------------------------------------------------------------------

# Phase 10 --- Vector Store

## Goal

Store and search dense vectors locally.

Preferred initial direction:

``` text
Qdrant
```

Reasons include local deployment, filtering, Docker friendliness,
metadata payloads, and production-quality vector search.

Reuse `backend/app/rag/vector_store.py` as the Mentra adapter boundary and extend it with the minimal operations required by ingestion/search. `QdrantVectorStore` currently owns client creation, collection creation/validation, and embedding identity checks; keep Qdrant-specific filters and payload details inside the adapter.

Required operations:

``` text
upsert chunks
delete document chunks
search
filter
reindex
health check
```

Qdrant payload should include enough identifiers/filters to recover
canonical metadata.

PostgreSQL is the authoritative document/chunk metadata store, accessed only through repositories. Qdrant holds vectors and retrieval payload needed for safe learner/context filtering; it is not the only source of document lifecycle truth. All learner-owned document metadata and retrieval operations must be scoped by internal `learner_id`.

------------------------------------------------------------------------

# Phase 11 --- Sparse Retrieval / BM25

## Goal

Complement semantic retrieval with lexical matching.

Dense retrieval is good for semantic similarity.

Sparse retrieval helps with:

``` text
exact terminology
acronyms
technical identifiers
rare keywords
course-specific vocabulary
```

Recommended architecture:

``` text
query
 â”œâ”€â”€ dense retrieval
 â””â”€â”€ sparse/BM25 retrieval
          â†“
       fusion
```

Implement only after baseline dense retrieval works and evaluation
infrastructure exists.

------------------------------------------------------------------------

# Phase 12 --- Hybrid Fusion

Use a deterministic fusion strategy such as Reciprocal Rank Fusion
initially.

``` text
dense results â”€â”€â”
                â”œâ”€â”€â–º RRF / fusion â”€â–º candidates
sparse results â”€â”˜
```

Fusion must preserve source identifiers and scores/ranks for debugging.

Do not ask an LLM to merge raw retrieval lists.

------------------------------------------------------------------------

# Phase 13 --- Reranking

## Goal

Improve precision of the final context sent to the LLM.

Pipeline:

``` text
retrieve broad candidate set
        â†“
hybrid fusion
        â†“
cross-encoder / reranker
        â†“
top K final chunks
```

Reranker should be independently configurable.

Example direction:

``` text
BGE reranker / compatible cross-encoder
```

Do not rerank the entire corpus.

------------------------------------------------------------------------

# Phase 14 --- Learning-Context-Aware Retrieval

## Goal

Stop old material from polluting current learning.

Retrieval priority:

``` text
ACTIVE
  â†“ highest

RELATED
  â†“ conditional

DORMANT
  â†“ excluded by default

ARCHIVED
  â†“ explicit only
```

Example:

``` text
Student studied Database Systems five months ago.
Current context = Python.

"Explain decorators."
```

Database notes should not appear.

But:

``` text
"Compare Python dictionaries to database tables."
```

may explicitly activate/use both contexts.

## Search contract

``` python
search(
    query: str,
    learner_id: str,
    context_ids: list[str] | None,
    concept_ids: list[str] | None,
    document_ids: list[str] | None,
    include_dormant: bool = False,
    limit: int = 8,
) -> RetrievalResult
```

Do not expose raw Qdrant filter syntax to callers.

------------------------------------------------------------------------

# Phase 15 --- Query Processing

Before retrieval, optionally perform:

``` text
normalization
query expansion
acronym handling
concept resolution
context resolution
```

Use expansion only when it measurably helps.

Avoid turning a simple query into five LLM calls.

The orchestration layer may already provide resolved contexts/concepts.
Reuse them rather than resolving everything twice.

------------------------------------------------------------------------

# Phase 16 --- Retrieval Modes

Support explicit modes where useful:

``` text
STANDARD
SOURCE_SPECIFIC
CONCEPT_FOCUSED
CROSS_CONTEXT
ASSESSMENT_GROUNDING
```

Modes should alter retrieval policy, not duplicate the entire
implementation.

------------------------------------------------------------------------

# Phase 17 --- Provenance and Citations

Every returned chunk must preserve enough provenance to identify its
source.

Minimum:

``` text
document_id
document title
chunk_id
page/slide/section where available
source location
```

Retrieval result:

``` json
{
  "content": "...",
  "document_id": "doc_42",
  "document_title": "Database Systems Lecture 6",
  "chunk_id": "chunk_211",
  "page": 14,
  "heading": "Third Normal Form",
  "score": 0.91
}
```

Never strip provenance and later ask the LLM to invent citations.

------------------------------------------------------------------------

# Phase 18 --- Public Retrieval Result

Return a domain object such as:

``` python
class RetrievedChunk:
    chunk_id: str
    document_id: str
    content: str
    score: float
    context_id: str | None
    concept_ids: list[str]
    source: SourceReference
```

And:

``` python
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    retrieval_mode: str
    grounded: bool
```

LangChain consumes this structure.

------------------------------------------------------------------------

# Phase 19 --- LangChain / LangGraph Integration

LangChain/LangGraph should call a RAG application/domain service that uses the existing `EmbeddingService`, repositories, and `VectorStore` abstraction:

``` python
RAGService.search(...)
```

not:

``` python
qdrant_client.search(...)
```

Typical flow:

``` text
TutoringGraph
   â†“
resolve intent
   â†“
Learner Engine
â†’ active contexts
â†’ relevant concepts
   â†“
RAGService.search(
    query,
    context_ids,
    concept_ids
)
   â†“
ranked grounded chunks
   â†“
ContextBuilder
   â†“
LLM
```

RAG does not construct the final LLM prompt.

------------------------------------------------------------------------

# Phase 20 --- Learner Engine Integration

RAG may consume:

``` text
canonical concept IDs
learning context IDs
context lifecycle
```

RAG must not consume:

``` text
mastery algorithm internals
retention formulas
raw learner evidence
```

Learner state may influence orchestration decisions such as what to
retrieve, but this decision should be passed through public contracts.

------------------------------------------------------------------------

# Phase 21 --- Document Lifecycle

## Goal

Handle old study material without deleting useful history.

Documents inherit/associate with learning contexts.

Example:

``` text
Python OOP Notes
context = Python
status = ACTIVE

Database Lecture 6
context = Database Systems
status = DORMANT
```

Dormant documents remain indexed or otherwise recoverable but are
excluded from normal retrieval.

Archive when explicitly old/irrelevant.

Delete only when requested or required by data policy.

## Reactivation

When a context becomes active again, its documents should become
eligible without requiring complete re-upload.

------------------------------------------------------------------------

# Phase 22 --- Reindexing and Versioning

Store:

``` text
parser_version
chunker_version
embedding_version
index_version
```

If chunking/embedding changes:

``` text
document
   â†“
reparse if needed
   â†“
rechunk
   â†“
re-embed
   â†“
replace index entries
```

Do not lose the original source merely because derived representations
change.

Reindexing should be resumable/idempotent.

------------------------------------------------------------------------

# Phase 23 --- Document Update Strategy

If a user uploads a revised document:

``` text
new file hash
   â†“
detect as new version or replacement
   â†“
invalidate old derived chunks if replacing
   â†“
ingest new version
```

Preserve history/version metadata if needed.

Do not allow stale chunks from replaced documents to remain silently
searchable.

------------------------------------------------------------------------

# Phase 24 --- Deletion

Deleting a document must remove:

``` text
document metadata as policy requires
chunks
dense vectors
sparse index entries
cached retrieval artifacts
```

Use a coordinated deletion workflow.

Avoid orphaned vectors.

------------------------------------------------------------------------

# Phase 25 --- Embedding Fine-Tuning

## Goal

Make embedding fine-tuning an evaluated improvement, not a checkbox.

Training data should use educational retrieval pairs:

``` text
query
positive passage
hard negatives
```

Sources may include:

``` text
Mentra evaluation corpus
course materials
synthetic educational queries reviewed/filtered
public educational datasets where licensing permits
```

Use hard-negative mining where appropriate.

Potential tooling:

``` text
FlagEmbedding / BGE training stack
```

## Compare

``` text
base embedding model
vs
fine-tuned model
```

Do not ship the fine-tuned model merely because training completed.

It must improve retrieval metrics or a meaningful downstream measure.

------------------------------------------------------------------------

# Phase 26 --- Retrieval Evaluation Dataset

Build a fixed evaluation set.

Each item:

``` text
query
relevant document/chunk IDs
optional context
optional concept
```

Include cases:

``` text
direct factual lookup
semantic paraphrase
acronyms
multi-section questions
similar but wrong passages
old/dormant material
cross-context query
source-specific query
```

Split training and evaluation data if fine-tuning embeddings.

------------------------------------------------------------------------

# Phase 27 --- Retrieval Metrics

Track:

``` text
Recall@K
MRR
nDCG
Precision@K where useful
context-filter accuracy
reranker lift
```

Also evaluate downstream:

``` text
answer groundedness
citation correctness
answer accuracy
irrelevant-context rate
```

A retrieval improvement is valuable only if it helps the actual tutoring
system.

------------------------------------------------------------------------

# Phase 28 --- Chunking Evaluation

Compare chunking strategies rather than assuming one is best.

Possible experiments:

``` text
fixed token chunks
heading-aware chunks
semantic chunks
heading + semantic hybrid
```

Measure retrieval quality and context efficiency.

Record chunker version.

------------------------------------------------------------------------

# Phase 29 --- OCR Evaluation

For OCR-heavy material track:

``` text
CER
WER
layout preservation
table extraction quality
downstream retrieval quality
```

OCR accuracy should be measured separately from retrieval quality.

A small OCR error may be harmless for retrieval; a structurally broken
extraction may not be.

------------------------------------------------------------------------

# Phase 30 --- Caching

Potential caches:

``` text
query embeddings
stable document parsing
chunk embeddings
retrieval results for identical short-lived queries
```

Invalidate appropriately when:

``` text
document status changes
context changes
document is replaced
index version changes
embedding model changes
```

Do not let cache bypass lifecycle filters.

------------------------------------------------------------------------

# Phase 31 --- Performance

Batch:

``` text
document embeddings
vector upserts
reindex operations
```

Avoid one network/database call per tiny chunk where batching is
supported.

For interactive retrieval optimize:

``` text
query embedding latency
vector search
sparse search
fusion
reranking
```

Track stage latency separately.

------------------------------------------------------------------------

# Phase 32 --- Failure Handling

### Parser failure

``` text
mark ingestion FAILED
store safe error metadata
allow retry
```

Do not partially mark document READY.

### OCR failure

Return ingestion failure or partial state according to policy.

### Embedding failure

Do not leave document marked fully indexed.

### Vector-store unavailable

Retrieval returns explicit service failure.

LangChain decides whether a non-RAG fallback is allowed.

### Reranker failure

Optionally fall back to fused retrieval if configured and safe.

Record degraded mode.

------------------------------------------------------------------------

# Phase 33 --- Observability

Trace:

``` text
document ingestion ID
parser selected
OCR usage
parse duration
chunk count
embedding duration
index duration
retrieval query
applied filters
dense result count
sparse result count
fusion ranks
reranker ranks
final chunk count
latency per stage
```

Do not log entire private documents unnecessarily.

------------------------------------------------------------------------

# Phase 34 --- Security and Privacy

Validate uploads.

Prevent unsafe path handling.

Keep local files/data local by default.

If external embedding/OCR services are ever introduced, they require an
explicit privacy/configuration decision.

Do not send whole documents to external LLMs when retrieval only
requires a few chunks.

------------------------------------------------------------------------

# Phase 35 --- Testing Strategy

## Unit tests

Test:

``` text
parser routing
cleaning
chunking
metadata preservation
filters
fusion
reranking adapters
lifecycle filtering
provenance
deduplication
versioning
```

## Integration tests

Test:

``` text
PDF â†’ parse â†’ chunk â†’ embed â†’ index â†’ retrieve
DOCX â†’ retrieve
PPTX â†’ retrieve
TXT â†’ retrieve
image/scanned PDF â†’ OCR â†’ retrieve
context switch â†’ old material excluded
cross-context query â†’ old relevant material included
document replacement â†’ stale chunks removed
delete â†’ vectors removed
```

## Fake stores

Provide fake embedding/vector/sparse implementations for deterministic
tests.

Do not require Qdrant or a model download for every unit test.

------------------------------------------------------------------------

# Phase 36 --- Required Scenario Tests

## Scenario A --- Old study material

Student has old Database Systems PDFs but currently studies Python.

Query:

``` text
"Explain Python decorators."
```

Expected:

``` text
Database material excluded by default.
```

## Scenario B --- Cross-context comparison

``` text
"How is a Python dictionary similar to a database table?"
```

Expected:

``` text
Python active material
+
relevant database material
```

may be retrieved.

## Scenario C --- Exact technical term

Query contains an acronym/rare identifier.

Expected:

``` text
hybrid retrieval should outperform dense-only where lexical signal matters.
```

## Scenario D --- Duplicate upload

Same file uploaded twice.

Expected:

``` text
detected safely;
no duplicate index pollution.
```

## Scenario E --- Replaced document

Expected:

``` text
old chunks no longer appear after successful replacement/reindex.
```

## Scenario F --- Citation

Retrieved claim must map back to actual source/page/section.

## Scenario G --- Vector store failure

Expected:

``` text
explicit retrieval failure;
no fabricated RAG result.
```

------------------------------------------------------------------------

# Phase 37 --- Agent Implementation Rules

AI coding agents must obey:

1.  Do not put learner mastery logic in RAG.
2.  Do not query learner tables directly.
3.  Do not let LangChain call Qdrant directly.
4.  Do not use raw LLM-generated concept names as durable chunk concept
    IDs.
5.  Do not flatten away source provenance.
6.  Do not OCR digital text unnecessarily.
7.  Do not use one arbitrary chunk size as unquestioned architecture.
8.  Do not search dormant/archived material by default.
9.  Do not delete old material merely because it is dormant.
10. Do not treat the vector store as the only document database.
11. Do not hard-code one embedding model into domain logic.
12. Do not hard-code Qdrant payload syntax into public service
    contracts.
13. Do not send the entire document corpus to the LLM.
14. Do not invent citations.
15. Do not leave stale vectors after replacement/deletion.
16. Do not mark ingestion READY before required index writes succeed.
17. Do not fine-tune embeddings without a base-vs-tuned evaluation.
18. Do not use evaluation data as training data.
19. Preserve version metadata for parser/chunker/embedding/index
    changes.
20. Add deterministic tests around retrieval policy.

------------------------------------------------------------------------

# Phase 38 --- Public API Summary

Equivalent capabilities must exist:

``` python
# ingestion
ingest_document(...)
reindex_document(...)
replace_document(...)
delete_document(...)

# metadata/lifecycle
get_document(...)
list_documents(...)
update_document_context(...)
set_document_status(...)

# retrieval
search(...)
search_document(...)
get_source(...)
get_chunk(...)

# health/admin
get_index_health(...)
rebuild_index(...)
```

Public callers should not depend on vector-store implementation details.

------------------------------------------------------------------------

# Phase 39 --- Recommended Implementation Order

``` text
1. RAG contracts + facade
2. document/chunk persistence
3. upload validation + hashing
4. parser abstraction
5. PDF/DOCX/PPTX/TXT parsing
6. OCR routing
7. normalized intermediate document representation
8. cleaning
9. structure-aware chunking
10. embedding abstraction
11. Qdrant adapter
12. dense indexing/retrieval
13. provenance/citation objects
14. context-aware filters
15. LangChain integration
16. Learner concept/context integration
17. sparse/BM25 retrieval
18. hybrid fusion
19. reranking
20. document lifecycle/reactivation
21. replacement/deletion/reindex workflows
22. evaluation dataset + metrics
23. chunking experiments
24. embedding-model comparison
25. embedding fine-tuning if justified
26. OCR evaluation
27. caching/performance
28. observability
29. privacy/security pass
30. full integration tests
```

Every phase should include:

``` text
implementation
+ typed contracts
+ tests
+ migration where required
+ documentation
```

------------------------------------------------------------------------

# Architectural Invariants --- Do Not Violate

1.  **RAG owns source knowledge retrieval, not learner knowledge
    state.**
2.  **Learner Engine owns canonical learning contexts and concept
    identity.**
3.  **LangChain/LangGraph owns orchestration, not vector search
    internals.**
4.  **Every retrieved chunk preserves provenance.**
5.  **Historical material is preserved but excluded when contextually
    dormant.**
6.  **Dormant material can be reactivated when genuinely relevant.**
7.  **The vector store is an index, not the sole source of document
    truth.**
8.  **Embedding and vector-store implementations remain replaceable.**
9.  **Concept tags use canonical Mentra concept IDs.**
10. **Parsing, chunking, embedding, retrieval, fusion, and reranking are
    independently testable stages.**
11. **No fabricated citations.**
12. **No stale chunks after successful replacement/deletion.**
13. **Fine-tuning must beat or meaningfully improve upon a baseline
    before adoption.**
14. **Retrieval quality is measured, not assumed.**
15. **Context filtering occurs before unnecessary broad retrieval
    whenever possible.**
16. **Only the relevant subset of source material enters the LLM
    context.**

------------------------------------------------------------------------

# Definition of Done

The first complete Mentra RAG implementation is done when:

-   PDF, DOCX, PPTX, TXT, and image/scanned material can enter a common
    ingestion pipeline;
-   native extraction is preferred and OCR is routed only where
    required;
-   useful document structure and provenance survive parsing/chunking;
-   chunks can be embedded and indexed locally;
-   dense retrieval works behind a stable RAG service;
-   context filters prevent old unrelated material from polluting normal
    queries;
-   dormant material remains recoverable for explicit/cross-context
    questions;
-   canonical concept IDs can be attached without letting RAG invent
    concept identity;
-   LangChain can retrieve grounded chunks without accessing Qdrant
    directly;
-   source/page/section information survives through retrieval;
-   hybrid dense+sparse retrieval and reranking can be enabled and
    evaluated;
-   documents can be replaced, archived, reactivated, reindexed, and
    deleted without stale index data;
-   retrieval has a fixed evaluation dataset and measurable baseline;
-   base and fine-tuned embedding models can be compared objectively;
-   ingestion/retrieval failures are explicit and recoverable;
-   the subsystem remains replaceable at parser, embedding,
    sparse-search, reranker, and vector-store layers.

At that point Mentra's RAG is not merely a vector database attached to
an LLM. It is a **context-aware educational knowledge system with
lifecycle, provenance, measurable retrieval quality, and clean contracts
with the rest of Mentra.**
