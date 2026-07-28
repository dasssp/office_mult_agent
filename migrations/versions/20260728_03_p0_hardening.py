"""P0 tenant persistence hardening

Revision ID: 20260728_03
Revises: 20260728_02
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_03"
down_revision = "20260728_02"
branch_labels = None
depends_on = None


def _tenant_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    ]


def upgrade() -> None:
    op.add_column("files", sa.Column("sha256", sa.String(64), nullable=False, server_default=""))
    op.add_column("files", sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("files", sa.Column("file_type", sa.String(32), nullable=False, server_default=""))
    op.create_table(
        "meeting_minutes",
        sa.Column("id", sa.String(36), primary_key=True),
        *_tenant_columns(),
        sa.Column("meeting_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "meeting_id", name="uq_meeting_minutes_tenant"),
    )
    op.create_index("ix_meeting_minutes_tenant_id", "meeting_minutes", ["tenant_id"])
    op.create_index("ix_meeting_minutes_meeting_id", "meeting_minutes", ["meeting_id"])
    op.create_index("ix_meeting_minutes_status", "meeting_minutes", ["status"])
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        *_tenant_columns(),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("object_ref", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    op.create_index("ix_artifacts_tenant_id", "artifacts", ["tenant_id"])
    op.create_index("ix_artifacts_kind", "artifacts", ["kind"])


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("meeting_minutes")
    op.drop_column("files", "file_type")
    op.drop_column("files", "row_count")
    op.drop_column("files", "sha256")
