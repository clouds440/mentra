import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch
from app.vision import VisionError, VisionService, create_vision_service
from app.vision.providers.local import PopplerPDFPageRasterizer, TesseractImageOCR
from app.rag.errors import ExtractionError
from app.rag.parsers import NativeDocumentParser, capabilities, ocr_image, ocr_pdf_page


class VisionOCRTests(unittest.TestCase):
    def test_pdf_page_must_be_positive_integer_before_any_provider_work(self):
        ocr, raster = Mock(), Mock()
        service = VisionService(ocr, raster)
        for page in (0, -1, True, 1.5, '1'):
            with self.subTest(page=page), self.assertRaisesRegex(VisionError, 'positive integer'):
                service.extract_pdf_page_text(Path('notes.pdf'), page)
        raster.render_page.assert_not_called()
        ocr.extract_text.assert_not_called()

    def test_capabilities_probe_each_dependency_once(self):
        ocr, raster = Mock(), Mock()
        ocr.available.return_value = True
        VisionService(ocr, raster).capabilities()
        ocr.available.assert_called_once()
        raster.available.assert_called_once()

    def test_image_command_language_timeout_and_output_are_unchanged(self):
        path = Path('source.png')
        with patch('PIL.Image.open') as opened, patch('app.vision.providers.local.subprocess.run') as run:
            image = opened.return_value.__enter__.return_value
            image.width, image.height = 1200, 800
            run.return_value.stdout = b'  English text\n\xff'
            self.assertEqual(TesseractImageOCR().extract_text(path), '  English text\n\ufffd')
            image.verify.assert_called_once()
            run.assert_called_once_with(['tesseract', str(path), 'stdout', '-l', 'eng'], capture_output=True, timeout=45, check=True)

    def test_pixel_limit_rejects_before_running_ocr(self):
        with patch('PIL.Image.open') as opened, patch('app.vision.providers.local.subprocess.run') as run:
            image = opened.return_value.__enter__.return_value
            image.width, image.height = 30_000_001, 1
            with self.assertRaisesRegex(VisionError, 'Image exceeds the pixel limit.'):
                TesseractImageOCR().extract_text(Path('oversized.png'))
            run.assert_not_called()

    def test_exact_pixel_limit_is_still_accepted(self):
        with patch('PIL.Image.open') as opened, patch('app.vision.providers.local.subprocess.run') as run:
            image = opened.return_value.__enter__.return_value
            image.width, image.height = 30_000_000, 1
            run.return_value.stdout = b'text'
            self.assertEqual(TesseractImageOCR().extract_text(Path('limit.png')), 'text')

    def test_corrupt_images_do_not_run_ocr(self):
        with patch('PIL.Image.open', side_effect=OSError('invalid image')), patch('app.vision.providers.local.subprocess.run') as run:
            with self.assertRaises(OSError):
                TesseractImageOCR().extract_text(Path('invalid.png'))
            run.assert_not_called()

    def test_tool_failures_and_timeouts_keep_existing_exception_behavior(self):
        for error in (subprocess.TimeoutExpired('tesseract', 45), subprocess.CalledProcessError(1, 'tesseract')):
            with self.subTest(error=type(error)), patch('PIL.Image.open') as opened, patch('app.vision.providers.local.subprocess.run', side_effect=error):
                image = opened.return_value.__enter__.return_value
                image.width, image.height = 100, 100
                with self.assertRaises(type(error)):
                    TesseractImageOCR().extract_text(Path('source.png'))

    def test_pdf_rendering_command_is_unchanged(self):
        with patch('app.vision.providers.local.subprocess.run') as run:
            PopplerPDFPageRasterizer().render_page(Path('notes.pdf'), 3, Path('page'))
            run.assert_called_once_with(['pdftoppm', '-f', '3', '-l', '3', '-r', '120', '-singlefile', '-png', 'notes.pdf', 'page'],
                capture_output=True, check=True, timeout=30)

    def test_capabilities_preserve_missing_dependency_semantics(self):
        for tesseract, poppler, pillow in ((False, True, True), (True, False, True), (True, True, True), (True, True, False)):
            with self.subTest(tesseract=tesseract, poppler=poppler, pillow=pillow), \
                patch('app.vision.providers.local.shutil.which', side_effect=lambda tool: tool if {'tesseract':tesseract, 'pdftoppm':poppler}[tool] else None), \
                patch('app.vision.providers.local.importlib.util.find_spec', return_value=object() if pillow else None):
                result = create_vision_service().capabilities()
                self.assertEqual(result.image_ocr, tesseract)
                self.assertEqual(result.pdf_page_ocr, tesseract and poppler)
                self.assertEqual(result.image_formats, ('png', 'jpg') if tesseract and pillow else ())

    def test_facade_is_provider_independent_and_cleans_temporary_raster(self):
        ocr, raster = Mock(), Mock()
        ocr.extract_text.return_value = 'unchanged text\n'
        service = VisionService(ocr, raster)
        self.assertEqual(service.extract_pdf_page_text(Path('notes.pdf'), 4), 'unchanged text\n')
        output = raster.render_page.call_args.args[2]
        self.assertEqual(raster.render_page.call_args.args[:2], (Path('notes.pdf'), 4))
        ocr.extract_text.assert_called_once_with(output.with_suffix('.png'))
        self.assertFalse(output.parent.exists())

    def test_pdf_temporary_files_are_cleaned_on_ocr_failure(self):
        ocr, raster = Mock(), Mock()
        ocr.extract_text.side_effect = subprocess.TimeoutExpired('tesseract', 45)
        with self.assertRaises(subprocess.TimeoutExpired):
            VisionService(ocr, raster).extract_pdf_page_text(Path('notes.pdf'), 1)
        self.assertFalse(raster.render_page.call_args.args[2].parent.exists())

    def test_parallel_calls_use_separate_request_directories(self):
        barrier = Barrier(3)
        paths = []
        def render(_path, _page, output):
            paths.append(output)
            output.with_suffix('.png').write_bytes(b'image')
            barrier.wait(timeout=5)
        ocr = SimpleNamespace(extract_text=lambda path: path.read_bytes().decode())
        service = VisionService(ocr, SimpleNamespace(render_page=render))
        with ThreadPoolExecutor(max_workers=3) as executor:
            self.assertEqual(list(executor.map(lambda page: service.extract_pdf_page_text(Path('notes.pdf'), page), range(1, 4))), ['image'] * 3)
        self.assertEqual(len({path.parent for path in paths}), 3)
        self.assertTrue(all(not path.parent.exists() for path in paths))

    def test_rag_translates_only_safe_vision_errors(self):
        with patch('app.rag.parsers._vision') as vision:
            vision.extract_image_text.side_effect = VisionError('Image exceeds the pixel limit.')
            vision.extract_pdf_page_text.side_effect = VisionError('Image exceeds the pixel limit.')
            for call in (lambda: ocr_image(Path('source.png')), lambda: ocr_pdf_page(Path('source.pdf'), 1)):
                with self.assertRaisesRegex(ExtractionError, 'Image exceeds the pixel limit.'):
                    call()

    def test_rag_capabilities_and_cache_identity_keep_the_existing_shape(self):
        with patch('app.rag.parsers._vision') as vision, patch('app.rag.parsers.package_version', return_value='test'):
            vision.capabilities.return_value = SimpleNamespace(image_formats=('png', 'jpg'), image_ocr=True, pdf_page_ocr=True)
            vision.asset_revisions.return_value = (('Pillow', 'pillow'), ('tesseract', 'tesseract version'), ('pdftoppm', 'poppler version'))
            result = capabilities()
            self.assertEqual(result['formats'][-2:], ['png', 'jpg'])
            self.assertEqual(set(result), {'formats', 'image_ocr', 'scanned_pdf_ocr'})
            self.assertEqual(NativeDocumentParser().version,
                'native-local-ocr-v1:pypdf=test;python-docx=test;python-pptx=test;Pillow=pillow;tesseract=tesseract version;pdftoppm=poppler version')
