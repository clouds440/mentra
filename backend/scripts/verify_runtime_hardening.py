"""Non-root image acceptance using synthetic files and offline baked assets."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic
import unittest


class RuntimeTests(unittest.TestCase):
    def test_non_root_and_private_storage_preserve_original_bytes(self):
        from app.rag.storage import FileStorage
        self.assertEqual(os.getuid(), 10001)
        for root in ('/var/lib/mentra/materials', '/var/log/mentra'):
            with TemporaryDirectory(dir=root) as directory:
                store = FileStorage(directory)
                original = b'synthetic-original-audit-data'
                blob = store.store(io.BytesIO(original), 1024)
                self.assertEqual(store.path(blob['storage_key']).read_bytes(), original)
                self.assertEqual(store.path(blob['storage_key']).stat().st_mode & 0o777, 0o600)

    def test_baked_embedding_process_matches_existing_numerics_and_reaps(self):
        from app.core.config import Settings
        from app.rag.embedding_process import ProcessEmbeddingService
        from app.rag.embeddings import SentenceTransformerEmbeddingService
        settings = Settings(_env_file=None)
        started = monotonic()
        process = ProcessEmbeddingService(settings)
        self.addCleanup(process.close)
        reference = SentenceTransformerEmbeddingService(settings)
        query = 'Synthetic verification of study material.'
        expected = reference.embed_query(query)
        actual = process.embed_query(query)
        self.assertEqual(process.dimension, reference.dimension)
        self.assertEqual(process.model_version, reference.model_version)
        self.assertEqual(process.query_token_count(query), reference.query_token_count(query))
        self.assertLess(max(abs(a-b) for a, b in zip(expected, actual, strict=True)), 1e-6)
        self.assertEqual(len(process.embed_documents(['Synthetic source one.', 'Synthetic source two.'])), 2)
        process.close()
        self.assertIsNone(process._process)
        print(json.dumps(dict(check='embedding_numeric_equivalence', elapsed_seconds=round(monotonic()-started, 3))))

    def test_real_ocr_and_isolated_text_reader(self):
        from PIL import Image, ImageDraw, ImageFont
        from app.documents import create_document_reader
        reader = create_document_reader()
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'source.txt'
            path.write_text('Synthetic document verification.', encoding='utf-8')
            self.assertIn('Synthetic document verification.', reader.read(path, filename='source.txt').text)
            image = Image.new('RGB', (1000, 180), 'white')
            ImageDraw.Draw(image).text((30, 40), 'BACKEND AUDIT 12345', fill='black', font=ImageFont.load_default(size=48))
            path = Path(directory) / 'source.png'
            image.save(path)
            self.assertIn('12345', reader.read(path, filename='source.png').text)
            self.assertEqual(reader.capabilities()['ocr_languages'], ['eng'])

    def test_linux_cpu_limit_terminates_active_process(self):
        code = 'import resource\nresource.setrlimit(resource.RLIMIT_CPU,(1,1))\nwhile True: pass\n'
        process = subprocess.run([sys.executable, '-c', code], timeout=5, capture_output=True)
        self.assertLess(process.returncode, 0)

    def test_speech_offline_model_warms_and_closes(self):
        from app.core.config import Settings
        from app.speech.service import SpeechService
        service = SpeechService(Settings(_env_file=None, speech_model_path='/opt/mentra/models/speech'))
        self.addCleanup(service.close)
        service.warm()
        service.close()
        self.assertIsNone(service._process)


if __name__ == '__main__':
    unittest.main(verbosity=2)
