import importlib.util
import re
from app.documents.readers.images import EmbeddedImages


class DOCXReader:
    formats = ('docx',)
    def __init__(self, vision):
        self.vision = vision

    def available(self):
        return importlib.util.find_spec('docx') is not None

    def read(self, path, kind, max_pages):
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        from docx.oxml.ns import qn
        document = Document(path)
        blocks, warnings, heading = [], [], []
        embedded = EmbeddedImages(self.vision)
        def paragraph_images(paragraph):
            for blip in paragraph._p.xpath('.//a:blip'):
                relation_id = blip.get(qn('r:embed'))
                if not relation_id:
                    warnings.append('Linked document images are not fetched; inspect the original.')
                    continue
                part = paragraph.part.related_parts.get(relation_id)
                if part is None:
                    warnings.append('An embedded document image could not be located; inspect the original.')
                    continue
                text = embedded.read(part.blob, warnings, 'in this document')
                if text and text.casefold() not in paragraph.text.casefold():
                    blocks.append(dict(text=text, heading_path=heading[:], method='image_ocr'))
                    warnings.append('Document image text was read with English OCR; verify handwriting and equations.')
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                if block.style and block.style.name.startswith('Heading'):
                    match = re.search(r'(\d+)$', block.style.name)
                    level = int(match.group(1)) if match else 1
                    heading = heading[:max(0, level - 1)] + [block.text]
                blocks.append(dict(text=block.text, heading_path=heading[:]))
                paragraph_images(block)
            elif isinstance(block, Table):
                blocks.append(dict(text='\n'.join(' | '.join(c.text for c in row.cells) for row in block.rows), heading_path=heading[:]))
                visited = set()
                for row in block.rows:
                    for cell in row.cells:
                        if cell._tc in visited:
                            continue
                        visited.add(cell._tc)
                        for paragraph in cell.paragraphs:
                            paragraph_images(paragraph)
        warnings.append('Headers, footers, comments, drawing text and handwritten annotations may be incomplete; inspect the original.')
        return dict(blocks=blocks, warnings=warnings)
