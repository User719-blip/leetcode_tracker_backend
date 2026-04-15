"""add refresh token audit columns

Revision ID: 0003_refresh_token_audit_columns
Revises: 0002_add_refresh_tokens
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_refresh_token_audit_columns"
down_revision = "0002_add_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("revocation_reason", sa.String(length=64), nullable=True))
    op.add_column("refresh_tokens", sa.Column("revoked_by", sa.String(length=64), nullable=True))
    op.add_column("refresh_tokens", sa.Column("reused_detected_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_tokens", "reused_detected_at")
    op.drop_column("refresh_tokens", "revoked_by")
    op.drop_column("refresh_tokens", "revocation_reason")