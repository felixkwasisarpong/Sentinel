"""add approval status to tool_calls

Revision ID: b0b7f8a83c54
Revises: 
Create Date: 2026-02-03 22:34:39.592808

"""
from alembic import op
import sqlalchemy as sa


revision = 'b0b7f8a83c54'
down_revision = '487457f4dea0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tool_calls", sa.Column("status", sa.Text(), nullable=False, server_default="EXECUTED"))
    op.add_column("tool_calls", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tool_calls", sa.Column("approval_note", sa.Text(), nullable=True))

    pass


def downgrade():
    op.drop_column("tool_calls", "approval_note")
    op.drop_column("tool_calls", "approved_at")
    op.drop_column("tool_calls", "status")
    pass
