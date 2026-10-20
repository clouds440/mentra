import io
import unittest
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import select, update, func
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.files.service import now
from app.files.tables import assets, reads
from app.files.delivery import byte_range
from app.api.routes.files import router
from app.auth.dependencies import require_identity
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AppError
from app.chat.repositories.attachments import AttachmentRepository
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from testing.files import create_test_files
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class FilesTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.files = create_test_files(self.db.sessions)
        self.owner, self.other = learner_id("alice"), learner_id("bob")

    def stage(self, key="one", content=b"original text", purpose="chat"):
        return self.files.upload(
            self.owner, io.BytesIO(content), "notes.txt", purpose, key
        )

    def test_receipt_replay_conflict_and_wrong_owner(self):
        first = self.stage()
        self.assertEqual(self.stage()["id"], first["id"])
        self.assertEqual(self.files.provider.uploads, 1)
        with self.assertRaises(AppError) as error:
            self.stage(content=b"changed")
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(AppError):
            self.files.metadata(self.other, first["id"])
        self.assertEqual(self.files.read(self.owner, first["id"]), b"original text")
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(reads)), 0)

    def test_schema_rollback_refuses_registered_files(self):
        from alembic import command
        from app.db.migrate import migration_config

        original = self.stage()
        with self.assertRaisesRegex(
            RuntimeError, "Original bytes cannot be reconstructed"
        ):
            with self.db.engine.begin() as connection:
                command.downgrade(migration_config(connection), "20261017_0027")
        self.assertEqual(self.files.read(self.owner, original["id"]), b"original text")

    def test_binding_consumption_and_shared_original_retention(self):
        file = self.stage()
        repo = AttachmentRepository(self.db.sessions, self.files)
        attachment = repo.create(
            self.owner, file["filename"], self.files.metadata(self.owner, file["id"])
        )
        self.assertEqual(
            repo.create(
                self.owner,
                file["filename"],
                self.files.metadata(self.owner, file["id"]),
            )["id"],
            attachment["id"],
        )
        with self.db.sessions.begin() as session:
            with self.assertRaises(AppError):
                self.files.bind(
                    session,
                    self.other,
                    file["id"],
                    "chat",
                    dict(chat_attachment_id=attachment["id"]),
                )
        self.assertEqual(self.files.cleanup(), 0)
        repo.remove(self.owner, attachment["id"])
        self.assertEqual(self.files.cleanup(), 1)
        self.assertEqual(self.files.provider.objects, {})

    def test_cancel_expiry_and_live_read_lease(self):
        file = self.stage()
        with self.files.open_original(self.owner, file["id"]):
            self.files.cancel(self.owner, file["id"])
            self.assertEqual(self.files.cleanup(), 0)
        self.assertEqual(self.files.cleanup(), 1)
        with self.assertRaises(AppError):
            self.files.read(self.owner, file["id"])
        expiring = self.stage("expired")
        with self.db.sessions.begin() as session:
            session.execute(
                update(assets)
                .where(assets.c.id == expiring["id"])
                .values(expires_at=now() - timedelta(seconds=1))
            )
        self.assertEqual(self.files.cleanup(), 1)

    def test_provider_failure_is_retryable_and_deletion_retries(self):
        from unittest.mock import patch

        with patch.object(
            self.files.provider,
            "verify",
            side_effect=AppError("FILES_UNAVAILABLE", "retry", 503),
        ):
            with self.assertRaises(AppError):
                self.stage()
        file = self.stage()
        self.files.cancel(self.owner, file["id"])
        with patch.object(
            self.files.provider, "destroy", side_effect=RuntimeError("outage")
        ):
            self.assertEqual(self.files.cleanup(), 1)
        with self.db.sessions.begin() as session:
            row = (
                session.execute(select(assets).where(assets.c.id == file["id"]))
                .mappings()
                .one()
            )
            self.assertEqual(row["state"], "DELETE_PENDING")
            session.execute(
                update(assets).where(assets.c.id == file["id"]).values(retry_at=now())
            )
        self.assertEqual(self.files.cleanup(), 1)

    def test_original_delivery_auth_ranges_and_deleted_conversation(self):
        file = self.stage()
        attachment = AttachmentRepository(self.db.sessions, self.files).create(
            self.owner, file["filename"], self.files.metadata(self.owner, file["id"])
        )
        conversation = str(uuid4())
        ChatRepository(self.db.sessions).begin_turn(
            self.owner,
            SendTurn(
                conversation_id=conversation,
                client_turn_id=uuid4(),
                expected_revision=0,
                content="file",
                attachment_ids=[attachment["id"]],
            ),
        )
        binding = self.files.binding(
            self.owner, file["id"], "chat", dict(chat_attachment_id=attachment["id"])
        )
        app = FastAPI()
        register_exception_handlers(app)
        app.state.files_service = self.files
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[require_identity] = lambda: SimpleNamespace(
            learner_id=self.owner
        )
        url = f"/api/v1/files/{file['id']}/content?binding_id={binding}"
        with TestClient(app) as client:
            response = client.get(url)
            self.assertEqual(response.content, b"original text")
            self.assertIn("no-store", response.headers["cache-control"])
            response = client.get(url, headers={"Range": "bytes=2-5"})
            self.assertEqual((response.status_code, response.content), (206, b"igin"))
            self.assertEqual(
                client.get(url, headers={"Range": "bytes=500-"}).status_code, 416
            )
            self.assertEqual(client.head(url).headers["content-length"], "13")
            app.dependency_overrides[require_identity] = lambda: SimpleNamespace(
                learner_id=self.other
            )
            self.assertEqual(client.get(url).status_code, 404)
            app.dependency_overrides[require_identity] = lambda: SimpleNamespace(
                learner_id=self.owner
            )
            from app.chat.repositories.tables import conversations

            with self.db.sessions.begin() as session:
                session.execute(
                    update(conversations)
                    .where(conversations.c.id == conversation)
                    .values(deleted_at=now())
                )
            self.assertEqual(client.get(url).status_code, 404)

    def test_range_parser(self):
        self.assertEqual(byte_range("bytes=-3", 10), (7, 9))
        self.assertEqual(byte_range("bytes=3-", 10), (3, 9))
        self.assertFalse(byte_range("bytes=1-2,4-5", 10))


if __name__ == "__main__":
    unittest.main()
