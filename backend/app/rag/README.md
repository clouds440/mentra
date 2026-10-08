# RAG implementation

The RAG module owns embedding inference and vector-store infrastructure independently of LangChain chat models.

`EmbeddingService` is the interface for query and document vectors. Its initial implementation loads the locally baked `BAAI/bge-small-en-v1.5` model, uses the BGE retrieval query instruction, and returns normalized vectors. `EMBEDDING_MODEL` and `EMBEDDING_DEVICE` configure it. The backend image downloads the model during build, and runtime loading is local-only.

`QdrantVectorStore` owns Qdrant client creation and collection validation. The collection dimension comes from the active `EmbeddingService`. A reserved collection point records model name, resolved model revision, and vector dimension; initialization refuses collections with a different identity or incompatible vector configuration. Reindex or explicitly migrate rather than reusing vectors after changing the model.

`RAGService` implements owned upload/replacement, context and concept policy, source access, dense/lexical RRF retrieval, optional reranking and typed source packets. PostgreSQL repositories own canonical metadata, immutable versions/generations/chunks, durable jobs, fencing and transactional publication. `python -m app.rag.worker` runs ingestion and reconciliation separately from the API. Parser and private-storage ports permit adapter replacement; configuration fingerprints include parser libraries and OCR binary revisions as well as embedding identity.

TXT, native/scanned/mixed PDF, DOCX, PPTX, PNG and JPEG are supported according to runtime capabilities. Image OCR and PDF-page rasterization are provided by the shared [Mentra Vision module](../vision/README.md); RAG owns document parsing, OCR routing and provenance. Office-image/speaker-note coverage and English OCR limitations are reported. Library and chat use authenticated APIs, stable version/generation citations, explicit archived-source consent and immediate authoritative deletion exclusion. Read the [setup and API contracts](../../../docs/rag.md) and [verification record](../../../docs/rag-verification.md).

Qdrant index identity is stored at `/_mentra_index_metadata` in a reserved point. Any future search implementation must exclude that marker point from user-facing results.
