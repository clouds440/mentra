"""Offline HTML extraction; never execute scripts or fetch referenced URLs."""
import base64
import binascii
import re
import importlib.util
from app.documents.errors import DocumentReadError
from app.documents.readers.images import EmbeddedImages

BOUNDARIES = {'p', 'div', 'section', 'article', 'li', 'tr', 'br', 'pre', 'blockquote', 'hr', *('h' + str(n) for n in range(1, 7))}


class _HTMLContent:
    def __init__(self, vision):
        self.blocks, self.warnings, self.buffer, self.heading = [], [], [], []
        self.embedded = EmbeddedImages(vision)
        self.pre, self.heading_level, self.code_tag, self.code_language = False, None, None, None

    def flush(self):
        text = ''.join(self.buffer)
        self.buffer.clear()
        text = text if self.pre or self.code_tag else re.sub(r'\s+', ' ', text).strip()
        if text.strip():
            if self.heading_level:
                self.heading = self.heading[:self.heading_level - 1] + [text]
            block = dict(text=text, heading_path=self.heading[:], method='native')
            if self.code_tag:
                block['language'] = self.code_language
            self.blocks.append(block)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag in ('script', 'style'):
            self.flush()
            self.code_tag = tag
            self.code_language = 'css' if tag == 'style' else 'json' if attrs.get('type') in ('application/json', 'application/ld+json') else 'js'
            if attrs.get('src'):
                self.warnings.append('External HTML scripts are not fetched; inline content is extracted.')
            return
        if tag in BOUNDARIES:
            self.flush()
        if tag == 'pre':
            self.pre = True
        if re.fullmatch(r'h[1-6]', tag):
            self.heading_level = int(tag[1])
        if tag in ('td', 'th'):
            self.buffer.append(' | ' if self.buffer else '')
        if tag == 'img':
            self.flush()
            alt = attrs.get('alt') or ''
            if alt:
                self.blocks.append(dict(text=alt, heading_path=self.heading[:], method='native'))
            source = attrs.get('src') or ''
            if source.startswith('data:image/') and ';base64,' in source:
                try:
                    encoded = source.split(',', 1)[1]
                    if len(encoded) > 40 * 1024 * 1024:
                        raise ValueError('embedded image exceeds limit')
                    data = base64.b64decode(encoded, validate=True)
                    extra = self.embedded.read(data, self.warnings, 'in this HTML document')
                    if extra and extra.casefold() != alt.strip().casefold():
                        self.blocks.append(dict(text=extra, heading_path=self.heading[:], method='image_ocr'))
                        self.warnings.append('HTML image text was read with English OCR; verify it against the source.')
                except (ValueError, binascii.Error):
                    self.warnings.append('An embedded HTML image could not be decoded; inspect the original.')
            else:
                self.warnings.append('Referenced HTML images are not fetched; only embedded image bytes can be processed.')

    def handle_endtag(self, tag):
        if tag == self.code_tag:
            self.flush()
            self.code_tag, self.code_language = None, None
            return
        if tag in BOUNDARIES:
            self.flush()
        if tag == 'pre':
            self.pre = False
        if re.fullmatch(r'h[1-6]', tag):
            self.heading_level = None

    def handle_data(self, data):
        self.buffer.append(data)

    def handle_comment(self, data):
        self.flush()
        self.blocks.append(dict(text='<!--' + data + '-->', heading_path=self.heading[:], method='native', language='html'))

    def extract(self, text):
        from bs4 import BeautifulSoup, Comment, NavigableString, Tag
        soup = BeautifulSoup(text, 'html.parser')
        # Explicitly include Script, Stylesheet and Template strings; get_text()
        # excludes these by default. Iterative traversal tolerates deep nesting.
        stack = [(soup, False)]
        while stack:
            node, closing = stack.pop()
            if isinstance(node, Comment):
                self.handle_comment(str(node))
            elif isinstance(node, NavigableString):
                self.handle_data(str(node))
            elif isinstance(node, Tag):
                if closing:
                    self.handle_endtag(node.name)
                    continue
                self.handle_starttag(node.name, node.attrs.items())
                if node.name in ('script', 'style'):
                    self.handle_data(''.join(str(part) for part in node.descendants if isinstance(part, NavigableString)))
                    self.handle_endtag(node.name)
                else:
                    stack.append((node, True))
                    stack.extend((child, False) for child in reversed(node.contents))
        self.flush()


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class HTMLReader:
    formats = ('html',)
    def __init__(self, vision):
        self.vision = vision

    def available(self):
        return importlib.util.find_spec('bs4') is not None

    def read(self, path, kind, max_pages):
        with path.open(encoding='utf-8-sig', newline='') as source:
            text = source.read()
        if '\x00' in text:
            raise DocumentReadError('Binary content cannot be parsed as text.')
        parser = _HTMLContent(self.vision)
        parser.extract(text)
        return dict(blocks=parser.blocks, warnings=parser.warnings)
