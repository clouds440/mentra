import importlib.util
import io
from app.documents.errors import DocumentReadError
from app.documents.readers.images import EmbeddedImages, pdf_page_text


class PDFReader:
    formats = ('pdf',)
    def __init__(self, vision):
        self.vision = vision

    def available(self):
        return importlib.util.find_spec('pypdf') is not None

    def read(self, path, kind, max_pages):
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise DocumentReadError('Password-protected PDFs are unsupported. Upload an unlocked copy.')
        if len(reader.pages) > max_pages:
            raise DocumentReadError('PDF exceeds the page limit.')
        blocks, warnings = [], []
        capabilities = self.vision.capabilities()
        embedded = EmbeddedImages(self.vision, capabilities=capabilities)
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text(extraction_mode='layout') or ''
            images = page.images
            method = 'native'
            if len(text.strip()) < 25 and (not text.strip() or len(images)):
                if not capabilities.pdf_page_ocr:
                    if len(images):
                        raise DocumentReadError('This PDF needs OCR. The server OCR tools are unavailable.')
                    warnings.append(f'Page {number} has no readable native text and OCR is unavailable; check the original.')
                    blocks.append(dict(text=text, page=number, method=method))
                    continue
                text, method = pdf_page_text(self.vision, path, number), 'ocr'
                warnings.append(f'Page {number} was read with OCR; verify equations and handwriting.')
            if not text.strip():
                warnings.append(f'Page {number} has no readable text; check the original for missing content.')
            blocks.append(dict(text=text, page=number, method=method))
            if method == 'native' and capabilities.image_ocr:
                for image in images:
                    buffer = io.BytesIO()
                    image.image.save(buffer, format='PNG')
                    extra = embedded.read(buffer.getvalue(), warnings, f'on page {number}', strict=True)
                    if extra and extra.casefold() not in text.casefold():
                        blocks.append(dict(text=extra, page=number, method='image_ocr'))
                        warnings.append(f'Image text on page {number} was read with OCR; verify it against the source.')
            elif method == 'native' and len(images):
                warnings.append(f'Image text on page {number} was not extracted because OCR is unavailable.')
        return dict(blocks=blocks, warnings=warnings)
