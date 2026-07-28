"""durable async task queue

Revision ID: 20260728_04
Revises: 20260728_03
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_04"
down_revision = "20260728_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "background_tasks",
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("background_tasks", sa.Column("result", sa.JSON(), nullable=True))
    op.add_column(
        "background_tasks",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "background_tasks",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "background_tasks",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "background_tasks",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "background_tasks",
        sa.Column("locked_by", sa.String(128), nullable=True),
    )
    op.add_column(
        "background_tasks",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "background_tasks",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_background_tasks_claim",
        "background_tasks",
        ["status", "available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_background_tasks_claim", table_name="background_tasks")
    for column in (
        "finished_at",
        "cancel_requested",
        "locked_by",
        "locked_at",
        "available_at",
        "max_attempts",
        "attempts",
        "result",
        "payload",
    ):
        op.drop_column("background_tasks", column)
