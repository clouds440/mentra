"""Opt-in Cloudinary + PostgreSQL contract check using a disposable schema.

PYTHONPATH=backend TEST_DATABASE_URL=... python backend/scripts/verify_files_cloudinary.py
Only synthetic originals and assets created in this run are uploaded/deleted.
"""

import hashlib
import io
import json
from uuid import uuid4
from sqlalchemy import select
from PIL import Image
from app.core.config import settings
from app.files.provider import CloudinaryProvider
from app.files.service import FilesService
from app.files.tables import assets
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


def main():
    config = settings.model_copy(update={"app_env": "verification-" + uuid4().hex[:12]})
    provider = CloudinaryProvider(config)
    rows = []
    with PostgresSandbox() as database:
        files = FilesService(database.sessions, provider, config)
        try:
            fixtures = [
                ("Dockerfile", b"FROM scratch\n"),
                ("source.py", b"def square(x):\n    return x*x\n"),
                ("notes.txt", "Unicode original: علم\n".encode()),
                ("types.ts", b"export type Name = { value: string };\r\n"),
                ("script.js", b"export const square = x => x * x;\n"),
                ("index.php", b"<?php echo 'original source'; ?>\n"),
                ("theme.css", b"body { color: #123456; }\r\n"),
                ("page.html", b"<!doctype html><script>throw 'never execute';</script><p>Original</p>\n"),
                ("data.json", b'{"original": true, "items": [1, 2]}\n'),
                ("component.tsx", b"export const App = () => <div>Source</div>;\n"),
                ("component.jsx", b"export default () => <p>Source</p>;\n"),
                ("config.yaml", b"service:\n  name: mentra\n"),
                (".env", b"SYNTHETIC_NON_SECRET=fixture\n"),
                ("Makefile", b"all:\n\t@echo source\n"),
            ]
            for kind in ("PNG", "JPEG", "GIF", "WEBP"):
                output = io.BytesIO()
                Image.new("RGB", (32, 32), "blue").save(output, format=kind)
                fixtures.append(("image." + kind.lower(), output.getvalue()))
            for filename, data in fixtures:
                uploaded = files.upload(
                    learner_id("alice"),
                    io.BytesIO(data),
                    filename,
                    "chat",
                    str(uuid4()),
                )
                fetched = files.read(learner_id("alice"), uploaded["id"])
                assert fetched == data
                row = files.metadata(learner_id("alice"), uploaded["id"])
                assert row["public_id"].startswith("mentra/" + config.app_env + "/")
                assert row["filename"] == filename
                assert (
                    files.receipt(learner_id("alice"), row["request_key"])["id"]
                    == uploaded["id"]
                )
                rows.append(
                    dict(
                        filename=filename,
                        size_bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                        passed=True,
                    )
                )
                print(filename+': exact bytes and filename verified',flush=True)
                files.cancel(learner_id('alice'),uploaded['id'])
                assert files.cleanup()==1
            print(
                json.dumps(
                    dict(
                        passed=True, fixtures=rows, namespace="mentra/" + config.app_env
                    ),
                    ensure_ascii=True,
                )
            )
        finally:
            # Exactly this fixture's schema owns this list; never enumerate or
            # delete all Cloudinary assets in the shared account.
            with database.sessions() as session:
                created = list(session.execute(select(assets).where(assets.c.state!='DELETED')).mappings())
            for row in created:
                assert row["public_id"].startswith("mentra/" + config.app_env + "/")
                provider.destroy(row)
            provider.close()


if __name__ == "__main__":
    main()
