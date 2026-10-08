from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Listing,
    ListingStatus,
    ListingSubmission,
    ListingSubmissionPhoto,
    ModerationDecision,
    ModerationDecisionStatus,
    User,
    UserRole,
    utc_now,
)


@dataclass(frozen=True)
class PhotoSnapshot:
    storage_key: str
    original_filename: str
    content_type: str


def create_submission(
    session: Session,
    listing: Listing,
    photos: list[PhotoSnapshot],
    submitted_at: datetime | None = None,
) -> ListingSubmission:
    if listing.status not in {ListingStatus.DRAFT, ListingStatus.REJECTED}:
        raise ValueError("Only drafts and rejected listings can be submitted")

    latest_version = session.scalar(
        select(func.max(ListingSubmission.version)).where(
            ListingSubmission.listing_id == listing.id
        )
    )
    submission_data = {
        "listing": listing,
        "version": (latest_version or 0) + 1,
        "title": listing.title,
        "description": listing.description,
        "price": listing.price,
        "category_name": listing.category.name,
        "category_slug": listing.category.slug,
    }
    if submitted_at is not None:
        submission_data["submitted_at"] = submitted_at

    submission = ListingSubmission(**submission_data)
    submission.photos = [
        ListingSubmissionPhoto(
            storage_key=photo.storage_key,
            original_filename=photo.original_filename,
            content_type=photo.content_type,
            position=position,
        )
        for position, photo in enumerate(photos)
    ]
    listing.status = ListingStatus.PENDING
    session.add(submission)
    session.flush()
    return submission


def record_moderation_decision(
    session: Session,
    submission: ListingSubmission,
    moderator: User,
    status: ModerationDecisionStatus,
    reason: str | None = None,
    decided_at: datetime | None = None,
) -> ModerationDecision:
    if status not in {
        ModerationDecisionStatus.APPROVED,
        ModerationDecisionStatus.REJECTED,
    }:
        raise ValueError("Unsupported moderation decision")
    if moderator.role is not UserRole.MODERATOR:
        raise PermissionError("Only moderators can decide submissions")
    if submission.listing.status is not ListingStatus.PENDING:
        raise ValueError("Only pending listings can receive a decision")
    if submission.decision is not None:
        raise ValueError("A decision already exists for this submission")

    decision_time = decided_at or utc_now()
    if status is ModerationDecisionStatus.REJECTED:
        if reason is None or not reason.strip():
            raise ValueError("A rejection reason is required")
        submission.listing.status = ListingStatus.REJECTED
    else:
        submission.listing.status = ListingStatus.PUBLISHED
        submission.listing.published_at = decision_time

    decision = ModerationDecision(
        submission=submission,
        moderator=moderator,
        status=status,
        reason=reason.strip() if reason else None,
    )
    decision.decided_at = decision_time
    session.add(decision)
    session.flush()
    return decision


def can_view_history(listing: Listing, viewer: User) -> bool:
    return viewer.role is UserRole.MODERATOR or listing.author_id == viewer.id


def get_listing_history(
    session: Session,
    listing_id: int,
    viewer: User,
) -> list[ListingSubmission]:
    listing = session.scalar(
        select(Listing)
        .options(
            selectinload(Listing.submissions).selectinload(ListingSubmission.photos),
            selectinload(Listing.submissions).selectinload(
                ListingSubmission.decision
            ),
        )
        .where(Listing.id == listing_id)
    )
    if listing is None:
        raise LookupError("Listing not found")
    if not can_view_history(listing, viewer):
        raise PermissionError("Listing history is not available to this user")
    return sorted(listing.submissions, key=lambda item: item.version)


def photo_is_in_submission_history(session: Session, storage_key: str) -> bool:
    photo_id = session.scalar(
        select(ListingSubmissionPhoto.id)
        .where(ListingSubmissionPhoto.storage_key == storage_key)
        .limit(1)
    )
    return photo_id is not None
