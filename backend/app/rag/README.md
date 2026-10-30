# RAG implementation

The RAG module owns embedding inference and vector-store infrastructure independently of LangChain chat models.

`EmbeddingService` is the interface for query and document vectors. Its implementation loads the locally baked `intfloat/multilingual-e5-small` model and returns normalized 384-dimensional vectors. Prefix handling belongs exclusively to the embedding service: `embed_query` applies `query: `, `embed_documents` applies `passage: `, and `embed_similarity` applies `query: ` to both sides of symmetric comparisons. Existing prefixes are stripped before applying the requested role. Token counting includes the role prefix; callers pass plain text. `EMBEDDING_MODEL` and `EMBEDDING_DEVICE` configure it. The backend image downloads the model during build, and runtime loading is local-only.

`QdrantVectorStore` owns Qdrant client creation and collection validation. The collection dimension comes from the active `EmbeddingService`. A reserved collection point records model name, resolved model revision, and vector dimension; initialization refuses collections with a different identity or incompatible vector configuration. Use the explicit operator reset below instead of reusing vectors after changing the model.

`RAGService` implements owned upload/replacement, context and concept policy, source access, dense/lexical RRF retrieval, optional reranking and typed source packets. PostgreSQL repositories own canonical metadata, immutable versions/generations/chunks, durable jobs, fencing and transactional publication. `python -m app.rag.worker` runs ingestion and reconciliation separately from the API. Parser and private-storage ports permit adapter replacement; configuration fingerprints include parser libraries and OCR binary revisions as well as embedding identity.

TXT, native/scanned/mixed PDF, DOCX, PPTX, PNG and JPEG are supported according to runtime capabilities. Image OCR and PDF-page rasterization are provided by the shared [Mentra Vision module](../vision/README.md); RAG owns document parsing, OCR routing and provenance. Office-image/speaker-note coverage and English OCR limitations are reported. Library and chat use authenticated APIs, stable version/generation citations, explicit archived-source consent and immediate authoritative deletion exclusion. Read the [setup and API contracts](../../../docs/library/rag.md) and [verification record](../../../docs/library/rag-verification.md).

Qdrant index identity is stored at `/_mentra_index_metadata` in a reserved point. Any future search implementation must exclude that marker point from user-facing results.

## E5 reset and verification

The only dense embedding consumers are RAG ingestion and RAG retrieval. Library semantic search, chat tools and assessment grounding share those paths. History memory uses PostgreSQL full-text/substring search; learner lookups do not embed text. They have no BGE vectors to remove.

Text in every language is accepted; there is no application language allowlist. English, Urdu and Arabic are the priority regression fixtures, not a restriction on ingestion or search.

CPU PyTorch inference, one reusable inference process per service, 32-item batching, normalized vectors, thread limits, and the model/revision-aware query cache are retained. There was no embedding ONNX/INT8 backend; speech INT8 is separate and unchanged.

Stop API/ingestion/assessment services before the destructive reset. After building the E5 image:

```sh
docker compose stop backend rag-worker assessment-worker
docker compose build backend
docker compose run --rm --no-deps backend python -m scripts.rag_admin reset-embeddings
docker compose run --rm --no-deps backend python -m scripts.rag_admin reset-embeddings --apply
docker compose up -d --force-recreate backend rag-worker assessment-worker
```

The reset deletes only the configured Qdrant collection (including all old/superseded vectors and payload indexes), recreates its E5 identity/indexes, cancels pending ingestion under the old configuration, and queues fresh generations from each non-deleted document's latest stored version, including archived and pending documents. Archived flags remain intact. Files, extracted content, source chunks/citations, memories and other PostgreSQL records are retained. Ordinary rebuild behavior remains unchanged. Each reset starts a new run; after a partial failure rerun the command with services still stopped. Never run an old BGE image against the reset collection.

Run `python -m scripts.rag_admin health` after the ingestion queue drains to check configuration and coverage. For the real-model CPU test, run `python -m scripts.verify_multilingual_embeddings`: it checks 27 top-1 retrieval cases across all English/Urdu/Arabic query and corpus language pairs using local Qdrant. This is a small regression corpus, not a general retrieval benchmark.

If an original file is already missing and there is no saved full extraction, the reset can rebuild from complete published text chunks for that exact version. It reconstructs the retained text blocks, rechunks with the E5 tokenizer, and attaches a missing-original warning to the new generation. Existing version metadata and old citation chunks remain intact; this does not recover the missing original file.

Prefix policy follows the [official E5 model card](https://huggingface.co/intfloat/multilingual-e5-small).

## Local multilingual reranking

The optional `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` cross-encoder reranks owned, hydrated E5/hybrid candidates. Copy the four `RAG_RERANKER_*` values from `.env.example` and follow the [setup instructions](../../../docs/getting-started/SETUP.md#optional-local-multilingual-reranker) to rebuild and enable it. Model weights/tokenizer are baked at a resolved revision; inference is CPU-only, local-only, and never enables remote model code. This PyTorch integration keeps the existing worker, batching, timeout and fallback architecture. ONNX is not enabled.

The default 20-candidate cap bounds CPU work. Queries and passages are sent as plain pairs without E5 prefixes; no embedding changes or vector rebuild are needed. All languages remain accepted. English, Urdu and Arabic are priority regression fixtures, not a language restriction.

`tests/rag/test_reranker_real.py` is an opt-in end-to-end test requiring `TEST_DATABASE_URL` for a disposable PostgreSQL database, plus local `TEST_EMBEDDING_PATH` and `TEST_RERANKER_PATH`. It ingests nine synthetic documents through the files/RAG worker, uses real E5 vectors with local Qdrant, and checks 27 monolingual/cross-language reranking/search cases, document scoping, worker reuse and fallback. See [real-model results](../../../docs/library/verification/reranker-real-verification.json). This small regression corpus is not a broad retrieval-quality benchmark.
