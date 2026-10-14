import io
import os
import tempfile
import time
import unittest
from app.rag.storage import FileStorage


class StorageSweepTests(unittest.TestCase):
    def test_active_upload_is_protected_until_receipt_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = FileStorage(directory)
            self.addCleanup(storage.close)
            with storage.staged_store(io.BytesIO(b'original'), 1024) as blob:
                path = storage.path(blob['storage_key'])
                os.utime(path, (time.time() - 100, time.time() - 100))
                storage.sweep_unknown_batch(lambda keys: set(), 1)
                self.assertEqual(path.read_bytes(), b'original')
            storage.sweep_unknown_batch(lambda keys: {blob['storage_key']}, 1)
            self.assertTrue(path.exists())
            for _ in range(2):
                storage.sweep_unknown_batch(lambda keys: set(), 1)
            self.assertFalse(path.exists())
