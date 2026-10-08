"""Stateless shared vision facade; no RAG, identity, database or job dependency."""
import tempfile
from pathlib import Path
from app.vision.ports import ImageOCR, PDFPageRasterizer
from app.vision.schemas import VisionCapabilities
from app.vision.errors import VisionError


class VisionService:
    def __init__(self, image_ocr: ImageOCR, pdf_rasterizer: PDFPageRasterizer):
        self._image_ocr = image_ocr
        self._pdf_rasterizer = pdf_rasterizer

    def capabilities(self) -> VisionCapabilities:
        ocr = self._image_ocr.available()
        return VisionCapabilities(image_ocr=ocr, image_formats=self._image_ocr.supported_formats() if ocr else (),
            pdf_page_ocr=ocr and self._pdf_rasterizer.available())

    def asset_revisions(self) -> tuple[tuple[str, str], ...]:
        return self._image_ocr.asset_revisions() + self._pdf_rasterizer.asset_revisions()

    def extract_image_text(self, path: Path) -> str:
        return self._image_ocr.extract_text(path)

    def extract_pdf_page_text(self, path: Path, page: int) -> str:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise VisionError('PDF page must be a positive integer.')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'page'
            self._pdf_rasterizer.render_page(path, page, output)
            return self.extract_image_text(output.with_suffix('.png'))
