"""initial persistence tables

Revision ID: 20260728_01
Revises:
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_01"
down_revision = None
branch_labels = None
depends_on = None


def _tenant_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    op.create_table("agent_threads", sa.Column("id", sa.String(length=128), primary_key=True), *_tenant_columns(), sa.Column("status", sa.String(length=32), nullable=False), sa.Column("state_ref", sa.String(length=512)))
    op.create_table("agent_runs", sa.Column("id", sa.String(length=36), primary_key=True), *_tenant_columns(), sa.Column("thread_id", sa.String(length=128), nullable=False), sa.Column("status", sa.String(length=32), nullable=False), sa.Column("intent", sa.String(length=64)), sa.Column("result_ref", sa.String(length=512)))
    op.create_table("audit_logs", sa.Column("id", sa.String(length=36), primary_key=True), *_tenant_columns(), sa.Column("action", sa.String(length=128), nullable=False), sa.Column("target_id", sa.String(length=128), nullable=False), sa.Column("trace_id", sa.String(length=128), nullable=False))
    op.create_table("approval_tasks", sa.Column("id", sa.String(length=36), primary_key=True), *_tenant_columns(), sa.Column("target_type", sa.String(length=64), nullable=False), sa.Column("target_id", sa.String(length=128), nullable=False), sa.Column("status", sa.String(length=32), nullable=False), sa.Column("comment", sa.Text()))
    op.create_table("reports", sa.Column("id", sa.String(length=36), primary_key=True), *_tenant_columns(), sa.Column("report_date", sa.String(length=10), nullable=False), sa.Column("status", sa.String(length=32), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.UniqueConstraint("tenant_id", "id", name="uq_reports_tenant_id"))
    op.create_table("files", sa.Column("id", sa.String(length=36), primary_key=True), *_tenant_columns(), sa.Column("filename", sa.String(length=512), nullable=False), sa.Column("content_type", sa.String(length=128)), sa.Column("byte_size", sa.Integer(), nullable=False), sa.Column("object_ref", sa.String(length=512)), sa.Column("status", sa.String(length=32), nullable=False))
    for table, column in (("agent_threads", "tenant_id"), ("agent_runs", "tenant_id"), ("agent_runs", "thread_id"), ("audit_logs", "tenant_id"), ("audit_logs", "action"), ("audit_logs", "target_id"), ("audit_logs", "trace_id"), ("approval_tasks", "tenant_id"), ("approval_tasks", "target_id"), ("reports", "tenant_id"), ("reports", "report_date"), ("reports", "status"), ("files", "tenant_id")):
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in ("files", "reports", "approval_tasks", "audit_logs", "agent_runs", "agent_threads"):
        op.drop_table(table)
