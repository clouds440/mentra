"""Document image-to-Vision handoff with request-local duplicate OCR reuse."""
import hashlib
import subprocess
import tempfile
from pathlib import Path
from app.documents.errors import DocumentReadError
from app.vision import VisionError


def image_text(vision, path):
    try:
        return vision.extract_image_text(path)
    except VisionError as exc:
        raise DocumentReadError(str(exc)) from exc


def pdf_page_text(vision, path, page):
    try:
        return vision.extract_pdf_page_text(path, page)
    except VisionError as exc:
        raise DocumentReadError(str(exc)) from exc


class EmbeddedImages:
    def __init__(self, vision, *, capabilities=None):
        self.vision = vision
        self.available = bool((capabilities if capabilities is not None else vision.capabilities()).image_formats)
        self.cache = {}

    def read(self, data: bytes, warnings: list[str], location: str, *, strict=False):
        if not self.available:
            warnings.append(f'Image text {location} was not extracted because OCR is unavailable.')
            return ''
        key = hashlib.sha256(data).hexdigest()
        if key not in self.cache:
            try:
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / 'image.png'
                    path.write_bytes(data)
                    self.cache[key] = image_text(self.vision, path).strip()
            except (DocumentReadError, OSError, ValueError, subprocess.SubprocessError):
                if strict:
                    raise
                warnings.append(f'An embedded image {location} could not be read; inspect the original.')
                self.cache[key] = None
        text = self.cache[key]
        if text is None:
            warnings.append(f'An embedded image {location} could not be read; inspect the original.')
            return ''
        if not text:
            warnings.append(f'An embedded image {location} has no readable text; inspect the original visual content.')
        return text


class ImageReader:
    formats = ('png', 'jpg')
    def __init__(self, vision):
        self.vision = vision

    def available(self):
        return bool(self.vision.capabilities().image_formats)

    def read(self, path, kind, max_pages):
        return dict(blocks=[dict(text=image_text(self.vision, path), method='ocr')],
            warnings=['This image was read with English OCR; verify handwriting and equations.'])
