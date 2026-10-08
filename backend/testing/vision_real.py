"""Verify standalone Mentra Vision with the existing real OCR fixtures in Docker."""
import json
import tempfile
from pathlib import Path
from app.vision import create_vision_service
from testing.rag_real import formats


def main():
    vision = create_vision_service()
    assert vision.capabilities().image_ocr and vision.capabilities().pdf_page_ocr
    fixtures = formats()
    results = []
    with tempfile.TemporaryDirectory() as folder:
        for number in (4, 5, 6):
            kind, data = fixtures[number]
            path = Path(folder) / f'fixture-{number}.{kind}'
            path.write_bytes(data)
            text = vision.extract_pdf_page_text(path, 1) if kind == 'pdf' else vision.extract_image_text(path)
            assert text.strip().lower() == 'python decorators wrap functions.', text
            results.append(dict(format=kind, text=text, matches_existing_fixture=True))
    print(json.dumps(dict(module='mentra vision', asset_revisions=dict(vision.asset_revisions()), checks=results), indent=2))


if __name__ == '__main__':
    main()
