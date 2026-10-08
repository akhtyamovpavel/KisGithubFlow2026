from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(str, Enum):
    USER = "user"
    MODERATOR = "moderator"


class ListingStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"


class ModerationDecisionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(
            UserRole,
            name="user_role",
            create_constraint=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=UserRole.USER,
    )

    listings: Mapped[list["Listing"]] = relationship(back_populates="author")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    listings: Mapped[list["Listing"]] = relationship(back_populates="category")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[ListingStatus] = mapped_column(
        SqlEnum(
            ListingStatus,
            name="listing_status",
            create_constraint=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=ListingStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User] = relationship(back_populates="listings")
    category: Mapped[Category] = relationship(back_populates="listings")
    submissions: Mapped[list["ListingSubmission"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class ListingSubmission(Base):
    __tablename__ = "listing_submissions"
    __table_args__ = (
        UniqueConstraint(
            "listing_id", "version", name="uq_submission_listing_version"
        ),
        CheckConstraint("version > 0", name="ck_listing_submission_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    category_name: Mapped[str] = mapped_column(String(100))
    category_slug: Mapped[str] = mapped_column(String(100))

    listing: Mapped[Listing] = relationship(back_populates="submissions")
    photos: Mapped[list["ListingSubmissionPhoto"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="ListingSubmissionPhoto.position",
    )
    decision: Mapped["ModerationDecision | None"] = relationship(
        back_populates="submission", cascade="all, delete-orphan", uselist=False
    )


class ListingSubmissionPhoto(Base):
    __tablename__ = "listing_submission_photos"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "position", name="uq_submission_photo_position"
        ),
        CheckConstraint("position >= 0", name="ck_submission_photo_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("listing_submissions.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(nullable=False)

    submission: Mapped[ListingSubmission] = relationship(back_populates="photos")


class ModerationDecision(Base):
    __tablename__ = "moderation_decisions"
    __table_args__ = (
        CheckConstraint(
            "status != 'rejected' OR coalesce(length(trim(reason)), 0) > 0",
            name="ck_moderation_rejection_reason",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("listing_submissions.id", ondelete="CASCADE"), unique=True
    )
    moderator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[ModerationDecisionStatus] = mapped_column(
        SqlEnum(
            ModerationDecisionStatus,
            name="moderation_decision_status",
            create_constraint=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    submission: Mapped[ListingSubmission] = relationship(back_populates="decision")
    moderator: Mapped[User] = relationship()
