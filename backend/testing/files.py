"""Test-only byte provider; production has no filesystem/object-store fallback."""

from contextlib import contextmanager
from io import BytesIO
import hashlib
from app.core.config import Settings
from app.files.service import FilesService


class MemoryFileProvider:
    environment = "test"

    def _ready(self):
        pass

    def __init__(self):
        self.objects = {}
        self.uploads = 0
        self.downloads = 0

    def upload(self, path, row):
        self.uploads += 1
        self.objects.setdefault(row["public_id"], path.read_bytes())
        return dict(asset_id=row["id"], version=1)

    def verify(self, row):
        data = self.objects[row["public_id"]]
        assert (
            len(data) == row["size_bytes"]
            and hashlib.sha256(data).hexdigest() == row["sha256"]
        )

    @contextmanager
    def stream(self, row, byte_range=None):
        self.downloads += 1
        data = self.objects[row["public_id"]]

        class Response:
            status_code = 200

            def iter_bytes(self, maximum):
                with BytesIO(data) as source:
                    while chunk := source.read(maximum):
                        yield chunk

        yield Response()

    def destroy(self, row):
        self.objects.pop(row["public_id"], None)

    def close(self):
        pass


def create_test_files(sessions, settings=None):
    return FilesService(sessions, MemoryFileProvider(), settings or Settings())
