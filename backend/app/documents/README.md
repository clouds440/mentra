# Mentra Documents

Reusable document extraction for Library/RAG, Chat uploads and other consumers. One facade detects supported files, dispatches independent format engines and returns native text plus embedded-image text from Mentra Vision. It imports no RAG, Learner, database or model orchestration code.

```python
from pathlib import Path
from app.documents import create_document_reader, DocumentReadError

reader = create_document_reader()
content = reader.read(Path('/private/upload'), filename='lesson.docx')
print(content.text)
# content.blocks: text, heading_path, page/slide, method and language where applicable
# content.warnings, content.format, content.media_type, content.reader_revision
```

The caller authorizes/stores the file and decides what to do with the result. This is a Python service API, not a new HTTP upload endpoint. RAG uses a thin compatibility adapter in `app/rag/parsers.py`; Chat can use the same facade without invoking indexing. Default reads run in a bounded, killable child process. Default limits are 25 MiB input, 200 PDF pages/slides, 5 million extracted characters and 120 seconds. Unsupported formats, encrypted PDFs and invalid UTF-8 receive explicit errors.

## Engines and worthwhile libraries

| Format | Implementation | Reason |
| --- | --- | --- |
| PDF | [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) | Existing native/layout extraction and embedded image access; scanned pages still need Vision OCR. |
| DOCX | [python-docx](https://python-docx.readthedocs.io/en/latest/) | Paragraphs, headings, tables and document relationships without implementing ZIP/XML decoding. |
| PPTX | [python-pptx](https://python-pptx.readthedocs.io/en/stable/) | Slide, grouped shape, table and image APIs without implementing the presentation format. |
| HTML/HTM | [Beautiful Soup 4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) with Python's HTML parser | Library owns the document tree; our traversal owns content/provenance policies. Explicit traversal includes inline script/style/template content that ordinary `get_text()` can exclude. |
| TXT | Python UTF-8 reader | Retains existing paragraph behavior; another parser adds no useful decoding. |
| Code/data/markup | Python UTF-8 reader | Preserves comments, indentation, blank lines and CRLF exactly instead of transforming or executing source. |
| PNG/JPEG and embedded images | Mentra Vision | Reuses local English Tesseract and poppler; no duplicate OCR implementation. |

[MarkItDown](https://github.com/microsoft/markitdown) handles many formats but targets Markdown conversion. Our current contract requires source blocks, location metadata and unchanged code rather than a new conversion contract. [Docling](https://docling-project.github.io/docling/usage/model_catalog/) offers advanced layout/table pipelines and also has a native model-free PDF pipeline. It is a possible future PDF engine when representative documents justify that complexity; it is not required to preserve the current verified extraction behavior. Neither is installed merely to wrap the libraries already in use.

Supported languages include Python, JavaScript/TypeScript/JSX/TSX, Java, C/C++, C#, Go, Rust, Ruby, PHP, Kotlin, Swift, Dart, Scala, Julia, R, Lua, Perl/Raku, Groovy, Elixir/Erlang, Haskell, OCaml, F#, Lisp/Scheme/Racket, Clojure, Zig, Nim, D, Pascal, Fortran, COBOL, Ada, Crystal, Tcl, Visual Basic, Solidity, Vyper, CUDA, Arduino, GDScript and shader/HDL languages. Shells, HTML, CSS preprocessors, Vue/Svelte/Astro, templates, SQL/GraphQL, notebooks as raw JSON, structured data, infrastructure/build configuration, markup and diffs are also supported.

`formats.py` is the authoritative registry of extensions, aliases and recognized basenames. Common aliases include `.hpp`, `.pyi`, `.mjs`, `.mts`, `.psm1`, `.tf`, `.tfvars`, `.jsonc` and `.yml`. Extensionless names include `Dockerfile`, `Containerfile`, `Makefile`, `Jenkinsfile`, `Gemfile`, `Procfile`, `.env`, `.gitignore` and `.editorconfig`; variants such as `Dockerfile.dev` and `.env.production` are recognized. `CMakeLists.txt` routes to the CMake source reader rather than paragraph splitting. Detection is case insensitive and checks content signatures before names. The Library picker permits extensionless files; server detection remains authoritative. These readers extract source text, not syntax trees or executed output. Legacy DOC/PPT, spreadsheets and arbitrary binaries are not advertised as supported.

## Content behavior

Native PDF, TXT and Office text keeps existing output conventions. DOCX body/table drawings and PPTX pictures, including grouped pictures, now pass their embedded bytes to Vision. HTML retains inline scripts/styles as separate code blocks, preformatted text, comments, hidden/template text and embedded base64 image OCR. Scripts are never executed and external image/script references are never fetched. Native source and image provenance accompany the result. Repeated identical embedded images invoke OCR once per document, while each occurrence retains its own location.

OCR failures on Office/HTML images produce warnings and retain native text. PDF OCR retains its prior strict failure behavior. OCR is English; this module does not yet interpret diagrams or classify images. DOCX headers/footers/comments, nested table drawings and presentation notes/charts/drawing text may be incomplete; warnings identify coverage limits. Code/data inputs currently require UTF-8, optionally with BOM.

## Composition and scaling

`service.py` orchestrates engines conforming to `ports.FormatReader`; `factory.py` wires providers; `readers/` owns format-specific adapters. `detection.py` validates signatures and bounds Office archives. `worker.py` and `isolation.py` own child-process limits/cancellation. Each request owns its temporary resources and OCR cache, allowing independent processes/replicas without shared extraction state. Consuming features still own admission control and durable jobs.

Inject engines or Vision with `create_document_reader(..., isolated=False)` for trusted in-process composition. The default isolated factory rejects custom providers rather than silently discarding them in a child. Engine adapters stay behind the same facade, so new format libraries can be added without changing consumers.

The new `documents-native-vision-v3` revision includes library and Vision asset versions. Added Office-image/HTML/code behavior intentionally changes new-ingestion identity. Existing published generations remain readable; jobs captured under an older parser fingerprint need a new reindex generation.

## Verification

Reader tests cover exact text/code behavior, scripts/styles/templates, embedded image routing/deduplication, provenance, missing/broken OCR, isolation, limits and the RAG adapter. `backend/testing/documents_real.py` checks 16 real-format fixtures through the default public API in the rebuilt backend image; results are recorded in [documents-verification.json](../../../docs/documents-verification.json). See [RAG verification](../../../docs/rag-verification.md) for downstream ingestion/search and packaged frontend/API/worker evidence.
