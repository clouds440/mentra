"""File registry. Original bytes never enter PostgreSQL."""

from sqlalchemy import (
    Table,
    Column,
    Text,
    Uuid,
    BigInteger,
    Integer,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata


assets = Table(
    "file_asset",
    metadata,
    Column("id", Uuid(as_uuid=False), primary_key=True),
    Column("learner_id", Uuid(as_uuid=False), ForeignKey("learner.id"), nullable=False),
    Column("purpose", Text, nullable=False),
    Column("request_key", Text, nullable=False),
    Column("filename", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("sha256", Text, nullable=False),
    Column("media_type", Text, nullable=False),
    Column("environment", Text, nullable=False),
    Column("public_id", Text, nullable=False),
    Column("resource_type", Text, nullable=False),
    Column("asset_id", Text),
    Column("version", BigInteger),
    Column("state", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("lease_until", DateTime(timezone=True)),
    Column("lease_token", Uuid(as_uuid=False)),
    Column("retry_at", DateTime(timezone=True)),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("error", Text),
    UniqueConstraint("learner_id", "id", name="uq_file_asset_owner_id"),
    UniqueConstraint("learner_id", "request_key", name="uq_file_asset_owner_key"),
    UniqueConstraint(
        "environment", "public_id", "resource_type", name="uq_file_asset_provider"
    ),
    CheckConstraint("size_bytes > 0", name="file_size"),
    CheckConstraint(
        "state IN ('UPLOADING','STAGED','ACTIVE','DELETE_PENDING','DELETED')",
        name="file_state",
    ),
    CheckConstraint("resource_type IN ('image','video','raw')", name="file_resource"),
    Index("idx_file_cleanup", "state", "expires_at", "retry_at"),
)

speech = Table(
    "file_speech_operation",
    metadata,
    Column("id", Uuid(as_uuid=False), primary_key=True),
    Column("learner_id", Uuid(as_uuid=False), ForeignKey("learner.id"), nullable=False),
    Column("result", JSONB),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("lease_token", Uuid(as_uuid=False)),
    Column("lease_until", DateTime(timezone=True)),
    UniqueConstraint("learner_id", "id"),
)

exports = Table(
    "file_export",
    metadata,
    Column("id", Uuid(as_uuid=False), primary_key=True),
    Column("learner_id", Uuid(as_uuid=False), ForeignKey("learner.id"), nullable=False),
    Column("event_id", Uuid(as_uuid=False), nullable=False),
    Column("event_revision", BigInteger, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("learner_id", "id"),
    ForeignKeyConstraint(
        ["learner_id", "event_id"],
        ["hm_event.learner_id", "hm_event.id"],
        ondelete="CASCADE",
    ),
)

bindings = Table(
    "file_binding",
    metadata,
    Column("id", Uuid(as_uuid=False), primary_key=True),
    Column("learner_id", Uuid(as_uuid=False), nullable=False),
    Column("file_id", Uuid(as_uuid=False), nullable=False),
    Column("purpose", Text, nullable=False),
    Column("chat_attachment_id", Uuid(as_uuid=False)),
    Column("document_version_id", Text),
    Column("assessment_attempt_id", Uuid(as_uuid=False)),
    Column("speech_operation_id", Uuid(as_uuid=False)),
    Column("export_id", Uuid(as_uuid=False)),
    Column("released_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["learner_id", "file_id"], ["file_asset.learner_id", "file_asset.id"]
    ),
    ForeignKeyConstraint(
        ["learner_id", "chat_attachment_id"],
        ["chat_attachment.learner_id", "chat_attachment.id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["learner_id", "document_version_id"],
        ["rag_document_version.learner_id", "rag_document_version.id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["learner_id", "assessment_attempt_id"],
        ["assessment_attempt.learner_id", "assessment_attempt.id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["learner_id", "speech_operation_id"],
        ["file_speech_operation.learner_id", "file_speech_operation.id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["learner_id", "export_id"],
        ["file_export.learner_id", "file_export.id"],
        ondelete="CASCADE",
    ),
    CheckConstraint(
        "num_nonnulls(chat_attachment_id,document_version_id,assessment_attempt_id,speech_operation_id,export_id) = 1",
        name="file_binding_target",
    ),
    CheckConstraint(
        "(purpose='chat' AND chat_attachment_id IS NOT NULL) OR (purpose='library' AND document_version_id IS NOT NULL) OR (purpose='assessment' AND assessment_attempt_id IS NOT NULL) OR (purpose='speech' AND speech_operation_id IS NOT NULL) OR (purpose='export' AND export_id IS NOT NULL)",
        name="file_binding_purpose",
    ),
    Index("idx_file_binding_asset", "file_id", "released_at"),
)

reads = Table(
    "file_read_lease",
    metadata,
    Column("id", Uuid(as_uuid=False), primary_key=True),
    Column(
        "file_id",
        Uuid(as_uuid=False),
        ForeignKey("file_asset.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Index("idx_file_read_asset", "file_id", "expires_at"),
)
