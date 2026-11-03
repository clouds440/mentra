import json
from pathlib import Path
import tempfile
import unittest

from app.rag.text_windows import token_windows
from model_assets import verify_manifest, write_manifest


class WindowAssetTests(unittest.TestCase):
    def test_exact_windows_cover_multilingual_text_and_fail_at_bound(self):
        for value in ('hello ' * 20, 'اردو عربی 中文' * 10, '🙂' * 50):
            parts = token_windows(value, lambda text: len(text.encode()), 20, max_windows=100)
            self.assertEqual(''.join(parts), value)
            self.assertTrue(all(len(part.encode()) <= 20 for part in parts))
        with self.assertRaisesRegex(ValueError, 'coverage'):
            token_windows('a' * 100, len, 10, max_windows=2)

    def test_manifest_detects_corruption_and_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'model-metadata.json').write_text(json.dumps(dict(model_name='test',model_version='revision')))
            weight=path/'weights.bin'; weight.write_bytes(b'original')
            write_manifest(path, role='embedding')
            self.assertTrue(verify_manifest(path))
            weight.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                verify_manifest(path)
            manifest=json.loads((path/'model-artifacts.json').read_text())
            manifest['files']={'../outside': 'hash'}
            (path/'model-artifacts.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'path'):
                verify_manifest(path)
