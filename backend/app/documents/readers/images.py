"""Document image-to-Vision handoff with request-local duplicate OCR reuse."""
import hashlib
import base64
from io import BytesIO
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


def pdf_page_text(vision, path, page, *, capture=None):
    try:
        return vision.extract_pdf_page_text(path, page,**({'capture':capture} if capture is not None else {}))
    except VisionError as exc:
        raise DocumentReadError(str(exc)) from exc


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class EmbeddedImages:
    def __init__(self, vision, *, capabilities=None):
        self.vision = vision
        self.available = bool((capabilities if capabilities is not None else vision.capabilities()).image_formats)
        self.cache = {}
        self.visuals = []
        self._visuals_by_key = {}
        self._visual_bytes = 0

    def capture(self, data, warnings, **location):
        """Bounded transient image payload; consuming domains persist files."""
        from PIL import Image, ImageStat
        key = hashlib.sha256(data).hexdigest()
        if key in self._visuals_by_key:
            item = self._visuals_by_key[key]
        else:
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 30_000_000:
                    raise DocumentReadError('Image exceeds the pixel limit.')
                if max(ImageStat.Stat(image.convert('RGB')).var) < .01:
                    return None  # Uniform empty scans/decorations are not diagrams.
                width,height = image.size
                media = 'image/png' if image.format=='PNG' else 'image/jpeg' if image.format=='JPEG' else None
                if media is None:
                    output=BytesIO(); image.save(output,'PNG'); data=output.getvalue(); media='image/png'
            if len(self.visuals)>=32 or len(data)>8*1024*1024 or self._visual_bytes+len(data)>24*1024*1024:
                warnings.append('Visual storage limit reached; inspect additional images in the original.')
                return None
            item=dict(key=key,media_type=media,width=width,height=height,
                sha256=hashlib.sha256(data).hexdigest(),data_base64=base64.b64encode(data).decode('ascii'),locations=[])
            self._visual_bytes+=len(data); self.visuals.append(item); self._visuals_by_key[key]=item
        point={name:value for name,value in location.items() if value is not None}
        if point not in item['locations']: item['locations'].append(point)
        return key

    def read(self, data: bytes, warnings: list[str], location: str, *, strict=False, **position):
        try:
            self.capture(data,warnings,**position)
        except (OSError,ValueError,DocumentReadError):
            if strict: raise
            warnings.append(f'An embedded image {location} could not be preserved; inspect the original.')
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


@workflow_logger.connect_module(default_outcome='success')
class ImageReader:
    formats = ('png', 'jpg')
    def __init__(self, vision):
        self.vision = vision

    def available(self):
        return bool(self.vision.capabilities().image_formats)

    def read(self, path, kind, max_pages):
        warnings=['This image was read with English OCR; verify handwriting and equations.']
        embedded=EmbeddedImages(self.vision)
        text=embedded.read(path.read_bytes(),warnings,'in this source',strict=True,block=0)
        return dict(blocks=[dict(text=text,method='ocr')],warnings=warnings,visuals=embedded.visuals)
