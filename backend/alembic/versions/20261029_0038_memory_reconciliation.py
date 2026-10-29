"""Evidence-preserving memory updates, revision snapshots and local search vectors."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "20261029_0038"
down_revision = "20261029_0037"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hm_memory", sa.Column("source_at", sa.DateTime(timezone=True)))
    op.add_column("hm_memory_revision", sa.Column("snapshot", pg.JSONB()))
    op.add_column(
        "hm_memory_evidence",
        sa.Column(
            "valid_from_revision", sa.BigInteger(), nullable=False, server_default="1"
        ),
    )
    op.add_column(
        "hm_memory_evidence", sa.Column("valid_until_revision", sa.BigInteger())
    )
    op.add_column(
        "hm_suppression",
        sa.Column("reason", sa.Text(), nullable=False, server_default="forgotten"),
    )
    op.execute(
        "UPDATE hm_memory m SET source_at=COALESCE((SELECT max(source_date) FROM hm_memory_evidence e WHERE e.learner_id=m.learner_id AND e.memory_id=m.id),m.confirmed_at,m.created_at)"
    )
    op.execute(
        "UPDATE hm_memory_evidence e SET valid_from_revision=m.revision FROM hm_memory m WHERE e.learner_id=m.learner_id AND e.memory_id=m.id"
    )
    op.execute(
        "UPDATE hm_memory_revision r SET snapshot=jsonb_build_object('content',m.content,'category',m.category,'origin',m.origin,'status',m.status,'pinned',m.pinned,'expires_at',m.expires_at) FROM hm_memory m WHERE r.learner_id=m.learner_id AND r.memory_id=m.id AND r.revision=m.revision"
    )
    op.create_table(
        "hm_memory_vector",
        sa.Column(
            "learner_id",
            pg.UUID(as_uuid=False),
            sa.ForeignKey("learner.id"),
            primary_key=True,
        ),
        sa.Column("memory_id", pg.UUID(as_uuid=False), primary_key=True),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("model_key", sa.Text(), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_id", "memory_id"],
            ["hm_memory.learner_id", "hm_memory.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM hm_memory_revision WHERE snapshot IS NOT NULL)"
        )
    ):
        raise RuntimeError(
            "Preserve memory history; roll forward rather than deleting revision snapshots."
        )
    op.drop_table("hm_memory_vector")
    op.drop_column("hm_suppression", "reason")
    op.drop_column("hm_memory_evidence", "valid_until_revision")
    op.drop_column("hm_memory_evidence", "valid_from_revision")
    op.drop_column("hm_memory_revision", "snapshot")
    op.drop_column("hm_memory", "source_at")
