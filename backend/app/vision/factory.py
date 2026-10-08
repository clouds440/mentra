"""Composition root; future provider selection belongs here, not in consumers."""
from app.vision.providers.local import PopplerPDFPageRasterizer, TesseractImageOCR
from app.vision.service import VisionService


def create_vision_service() -> VisionService:
    return VisionService(TesseractImageOCR(), PopplerPDFPageRasterizer())
