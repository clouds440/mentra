# RAG module

The RAG module is reserved for document ingestion, retrieval, and document intelligence workflows.

This module is intentionally separate from LangChain orchestration so the retrieval pipeline can evolve independently from LLM orchestration.

Planned responsibilities:

- document ingestion and storage
- PDF/DOCX/PPTX/TXT/image handling
- OCR and content extraction
- chunking and embedding generation
- semantic or hybrid retrieval
- vector database integrations
- reranking and retrieval evaluation

RAG should provide retrieval capabilities to the orchestration layer without embedding business logic directly in API routes.
