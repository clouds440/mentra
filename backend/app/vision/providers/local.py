"""Existing English Tesseract OCR and poppler rendering, without policy changes."""
import importlib.util
import shutil
import subprocess
from importlib.metadata import version as package_version, PackageNotFoundError
from pathlib import Path
from app.vision.errors import VisionError


def _tool_revision(command: list[str]) -> str:
    if not shutil.which(command[0]):
        return 'unavailable'
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=True)
        return (result.stdout or result.stderr).splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError, IndexError):
        return 'unknown'


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class TesseractImageOCR:
    def available(self) -> bool:
        return bool(shutil.which('tesseract'))

    def supported_formats(self) -> tuple[str, ...]:
        return ('png', 'jpg') if importlib.util.find_spec('PIL') else ()

    def extract_text(self, path: Path) -> str:
        from PIL import Image
        with Image.open(path) as image:
            if image.width * image.height > 30_000_000:
                raise VisionError('Image exceeds the pixel limit.')
            image.verify()
        result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng'], capture_output=True, timeout=45, check=True)
        return result.stdout.decode('utf-8', errors='replace')

    def asset_revisions(self) -> tuple[tuple[str, str], ...]:
        try:
            pillow = package_version('Pillow')
        except PackageNotFoundError:
            pillow = 'unavailable'
        return (('Pillow', pillow), ('tesseract', _tool_revision(['tesseract', '--version'])))


@workflow_logger.connect_module(default_outcome='success')
class PopplerPDFPageRasterizer:
    def available(self) -> bool:
        return bool(shutil.which('pdftoppm'))

    def render_page(self, path: Path, page: int, output: Path) -> None:
        subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-r', '120', '-singlefile', '-png', str(path), str(output)],
            capture_output=True, check=True, timeout=30)

    def asset_revisions(self) -> tuple[tuple[str, str], ...]:
        return (('pdftoppm', _tool_revision(['pdftoppm', '-v'])),)
