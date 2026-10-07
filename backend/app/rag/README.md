# RAG foundations

The RAG module owns embedding inference and vector-store infrastructure independently of LangChain chat models.

`EmbeddingService` is the interface for query and document vectors. Its initial implementation loads the locally baked `BAAI/bge-small-en-v1.5` model, uses the BGE retrieval query instruction, and returns normalized vectors. `EMBEDDING_MODEL` and `EMBEDDING_DEVICE` configure it. The backend image downloads the model during build, and runtime loading is local-only.

`QdrantVectorStore` owns Qdrant client creation and collection validation. The collection dimension comes from the active `EmbeddingService`. A reserved collection point records model name, resolved model revision, and vector dimension; initialization refuses collections with a different identity or incompatible vector configuration. Reindex or explicitly migrate rather than reusing vectors after changing the model.

The current foundation deliberately does not implement ingestion, chunking, search, or retrieval workflows. Future RAG callers should depend on `EmbeddingService` and a vector-store interface, not Sentence Transformers or Qdrant clients directly.

Qdrant index identity is stored at `/_mentra_index_metadata` in a reserved point. Any future search implementation must exclude that marker point from user-facing results.
