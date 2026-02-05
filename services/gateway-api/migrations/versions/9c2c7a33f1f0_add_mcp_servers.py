"""add mcp servers registry

Revision ID: 9c2c7a33f1f0
Revises: b0b7f8a83c54
Create Date: 2026-02-04 14:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "9c2c7a33f1f0"
down_revision = "b0b7f8a83c54"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "mcp_servers" in inspector.get_table_names():
        return
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("tool_prefix", sa.String(), nullable=False, unique=True),
        sa.Column("auth_header", sa.String(), nullable=True),
        sa.Column("auth_token", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("mcp_servers")
