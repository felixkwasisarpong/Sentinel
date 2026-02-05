"""add tool_call result and approved_by

Revision ID: c9b9e3a1a2f7
Revises: 7d5a3f6f2c1a
Create Date: 2026-02-05 13:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c9b9e3a1a2f7"
down_revision = "7d5a3f6f2c1a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tool_calls", sa.Column("approved_by", sa.String(), nullable=True))
    op.add_column("tool_calls", sa.Column("result", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tool_calls", "result")
    op.drop_column("tool_calls", "approved_by")
