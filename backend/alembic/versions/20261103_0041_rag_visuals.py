"""Retained diagram files and immutable generation/block provenance."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261103_0041"
down_revision = "20261103_0040"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "rag_visual",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("learner_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("version_id", sa.Text(), nullable=False),
        sa.Column("generation_id", sa.Text(), nullable=False),
        sa.Column("file_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("block_refs", JSONB, nullable=False),
        sa.Column("locations", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learner.id"]),
        sa.ForeignKeyConstraint(
            ["learner_id", "document_id", "version_id"],
            [
                "rag_document_version.learner_id",
                "rag_document_version.document_id",
                "rag_document_version.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["learner_id", "document_id", "generation_id"],
            [
                "rag_generation.learner_id",
                "rag_generation.document_id",
                "rag_generation.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["learner_id", "file_id"], ["file_asset.learner_id", "file_asset.id"]
        ),
        sa.UniqueConstraint("learner_id", "generation_id", "sha256"),
        sa.CheckConstraint(
            "width > 0 AND height > 0 AND width::bigint*height <= 30000000 AND media_type IN ('image/png','image/jpeg')",
            name="visual_format",
        ),
    )
    op.create_index(
        "idx_rag_visual_generation", "rag_visual", ["learner_id", "generation_id"]
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM rag_visual LIMIT 1")).first():
        raise RuntimeError(
            "Preserve or explicitly retire retained visual records before downgrading"
        )
    op.drop_table("rag_visual")
