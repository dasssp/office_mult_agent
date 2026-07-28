"""runtime service persistence

Revision ID: 20260728_02
Revises: 20260728_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_02"
down_revision = "20260728_01"
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
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(36), primary_key=True),
        *_tenant_columns(),
        sa.Column("operation", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.UniqueConstraint("tenant_id", "operation", "idempotency_key", name="uq_idempotency_scope"),
    )
    op.create_table(
        "user_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        *_tenant_columns(),
        sa.Column("memory_key", sa.String(128), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("tenant_id", "created_by", "memory_key", name="uq_user_memory_key"),
    )
    op.create_table(
        "background_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        *_tenant_columns(),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(128)),
    )
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(36), primary_key=True),
        *_tenant_columns(),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("cron", sa.String(128), nullable=False),
        sa.Column("task_type", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    )


def downgrade() -> None:
    for table in ("schedules", "background_tasks", "user_memories", "idempotency_records"):
        op.drop_table(table)
