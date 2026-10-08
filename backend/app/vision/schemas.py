from dataclasses import dataclass


@dataclass(frozen=True)
class VisionCapabilities:
    image_ocr: bool
    image_formats: tuple[str, ...]
    pdf_page_ocr: bool
