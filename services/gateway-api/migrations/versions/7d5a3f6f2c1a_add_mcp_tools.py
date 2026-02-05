"""add mcp tools

Revision ID: 7d5a3f6f2c1a
Revises: 9c2c7a33f1f0
Create Date: 2026-02-04 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "7d5a3f6f2c1a"
down_revision = "9c2c7a33f1f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_tools",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("server_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("mcp_servers.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("input_schema", sa.JSON(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_mcp_tools_server_id", "mcp_tools", ["server_id"])


def downgrade():
    op.drop_index("ix_mcp_tools_server_id", table_name="mcp_tools")
    op.drop_table("mcp_tools")
