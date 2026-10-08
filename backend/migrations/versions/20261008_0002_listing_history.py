"""Add immutable submission snapshots and moderation decisions.

Revision ID: 20261008_0002
Revises: 20261008_0001
Create Date: 2026-10-08 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20261008_0002"
down_revision = "20261008_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("category_name", sa.String(length=100), nullable=False),
        sa.Column("category_slug", sa.String(length=100), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_listing_submission_version"),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "listing_id", "version", name="uq_submission_listing_version"
        ),
    )
    op.create_index(
        "ix_listing_submissions_listing_id",
        "listing_submissions",
        ["listing_id"],
    )
    op.create_table(
        "listing_submission_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_submission_photo_position"),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["listing_submissions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "submission_id", "position", name="uq_submission_photo_position"
        ),
    )
    op.create_index(
        "ix_listing_submission_photos_submission_id",
        "listing_submission_photos",
        ["submission_id"],
    )
    op.create_table(
        "moderation_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("moderator_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "approved",
                "rejected",
                name="moderation_decision_status",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status != 'rejected' OR coalesce(length(trim(reason)), 0) > 0",
            name="ck_moderation_rejection_reason",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["listing_submissions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["moderator_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("submission_id"),
    )
    op.create_index(
        "ix_moderation_decisions_moderator_id",
        "moderation_decisions",
        ["moderator_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_moderation_decisions_moderator_id", table_name="moderation_decisions"
    )
    op.drop_table("moderation_decisions")
    op.drop_index(
        "ix_listing_submission_photos_submission_id",
        table_name="listing_submission_photos",
    )
    op.drop_table("listing_submission_photos")
    op.drop_index(
        "ix_listing_submissions_listing_id", table_name="listing_submissions"
    )
    op.drop_table("listing_submissions")
