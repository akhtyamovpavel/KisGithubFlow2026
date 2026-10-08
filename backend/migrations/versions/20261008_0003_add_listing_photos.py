"""Add listing photos.

Revision ID: 20261008_0003
Revises: 20261008_0002
Create Date: 2026-10-08 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20261008_0003"
down_revision = "20261008_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key", name="uq_listing_photos_storage_key"),
    )
    op.create_index(
        "ix_listing_photos_listing_id",
        "listing_photos",
        ["listing_id"],
    )

    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER listing_photos_limit_insert
            BEFORE INSERT ON listing_photos
            WHEN (
                SELECT COUNT(*)
                FROM listing_photos
                WHERE listing_id = NEW.listing_id
            ) >= 5
            BEGIN
                SELECT RAISE(ABORT, 'listing photo limit reached');
            END;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS listing_photos_limit_insert")

    op.drop_index("ix_listing_photos_listing_id", table_name="listing_photos")
    op.drop_table("listing_photos")
