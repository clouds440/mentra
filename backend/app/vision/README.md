# Mentra Vision

Shared, stateless image-processing module. Its current capabilities are exactly the OCR functionality extracted from RAG: English Tesseract image text extraction and poppler PDF-page rasterization followed by that same OCR. It has no RAG, Learner, LangChain, identity, persistence or HTTP dependency.

Consumers use the public facade:

```python
from pathlib import Path
from app.vision import create_vision_service

vision = create_vision_service()
capabilities = vision.capabilities()
text = vision.extract_image_text(Path('/private/source.png'))
page_text = vision.extract_pdf_page_text(Path('/private/source.pdf'), page=1)
```

The caller supplies an authorized local file. Image OCR returns the original decoded text, including whitespace; it does not normalize, strip, chunk or assign document provenance. PDF page numbers must be positive integers; invalid page arguments fail before rendering or creating temporary files. The caller owns document/page-range validation, routing, warnings, job policy and resource admission. RAG continues to perform those responsibilities in its bounded, killable parser subprocess.

## Preserved behavior

- PNG/JPEG advertised when Tesseract and Pillow are available.
- Pillow image validation and the same 30,000,000-pixel ceiling.
- Tesseract `stdout`, English (`eng`), 45-second tool timeout and UTF-8 replacement decoding.
- Poppler single-page PNG rendering at 120 DPI with the same 30-second tool timeout.
- One private temporary directory per PDF-page request, cleaned on success or failure.
- Existing missing-tool capability semantics, validation message and tool exception behavior. `VisionError` carries the safe pixel-limit message; RAG translates it to its existing `ExtractionError`.
- Asset revision reporting for Pillow/Tesseract/poppler. RAG's parser fingerprint retains its previous ordering and value, so extraction alone does not invalidate ingestion checkpoints or require reindexing.

RAG retains native PDF/DOCX/PPTX/TXT parsing, scanned/mixed-page detection, page/slide/heading provenance, warnings, limits and its outer subprocess cancellation. Embedded image OCR calls this shared service. No image recognition, CLIP, captions, new language or new endpoint is introduced in this extraction.

## Module boundaries and scaling

| File | Responsibility |
| --- | --- |
| `__init__.py` | Public consumer API |
| `service.py` | Capability orchestration, independent of providers and consumers |
| `ports.py` | Separate `ImageOCR` and `PDFPageRasterizer` contracts |
| `providers/local.py` | Existing local tool implementations |
| `schemas.py` / `errors.py` | Typed capabilities and module-owned validation error |
| `factory.py` | Default provider composition |

The facade has no mutable request state, global job queue or local result cache. Calls use separate temporary paths and independent tool processes; multiple worker processes/replicas can use it without coordinating vision state. Each replica needs the tool assets and access to its request's source file. Admission limits and durable orchestration remain with the consuming feature; statelessness does not imply unlimited safe OCR concurrency. The current deployment remains the existing API/worker architecture.

New capabilities should get their own typed results and provider protocols rather than adding unrelated methods to the OCR port. Add them to the facade and compose their providers in `factory.py`. Local or future remote providers can implement the same capability contracts; provider-specific libraries and model loading stay inside adapters. Future visual embeddings, image classification or description can therefore be added alongside OCR without making RAG own those implementations. This is an extension boundary, not a provisioned remote vision service or a new distributed queue.

## Verification

`backend/tests/vision/test_ocr.py` checks exact commands, limits, output and failure behavior, temporary cleanup, independent concurrent requests, provider substitution, and RAG capability/fingerprint/error compatibility. `backend/testing/vision_real.py` exercises the public facade with real PNG, JPEG and scanned-PDF fixtures. Its recorded output is [vision-verification.json](../../../docs/vision-verification.json).

The complete backend suite and real RAG format/runtime checks were rerun after extraction. See [RAG verification](../../../docs/rag-verification.md) for the preserved end-to-end contracts and test environment.
