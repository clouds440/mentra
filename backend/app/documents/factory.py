from app.documents.service import DocumentReader
from app.documents.readers.text import TextReader, CodeReader
from app.documents.readers.pdf import PDFReader
from app.documents.readers.docx import DOCXReader
from app.documents.readers.pptx import PPTXReader
from app.documents.readers.images import ImageReader
from app.documents.readers.html import HTMLReader
from app.vision import create_vision_service


def create_document_reader(*, vision=None, engines=None, isolated=True) -> DocumentReader:
    if isolated and (vision is not None or engines is not None):
        raise ValueError('Injected providers require isolated=False; subprocesses use the default composition.')
    vision = vision if vision is not None else create_vision_service()
    engines = engines if engines is not None else [TextReader(), PDFReader(vision), DOCXReader(vision),
        PPTXReader(vision), ImageReader(vision), HTMLReader(vision), CodeReader()]
    return DocumentReader(engines, vision, isolated=isolated)
