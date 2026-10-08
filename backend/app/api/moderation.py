from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import DatabaseSession, ModeratorUser
from app.media_storage import path_for_storage_key
from app.models import (
    Listing,
    ListingStatus,
    ListingSubmission,
    ListingSubmissionPhoto,
    ModerationDecision,
    ModerationDecisionStatus,
)
from app.services.history import record_moderation_decision
from app.services.listing_validation import RULES, rule_results, validate_listing

router = APIRouter(prefix="/moderation", tags=["moderation"])


class SubmissionPhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_type: str
    position: int


class SubmissionAuthorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    email: EmailStr


class ModerationQueueItemResponse(BaseModel):
    id: int
    listing_id: int
    version: int
    submitted_at: datetime
    title: str
    price: Decimal
    category_name: str
    category_slug: str
    author: SubmissionAuthorResponse
    photos: list[SubmissionPhotoResponse]


class ModerationRuleResponse(BaseModel):
    id: str
    field: str
    label: str
    passed: bool


class ModerationQueueDetailResponse(ModerationQueueItemResponse):
    description: str
    rules: list[ModerationRuleResponse]


class ModerationDecisionRequest(BaseModel):
    decision: ModerationDecisionStatus
    reason: str | None = None
    confirmed_rule_ids: list[str] = Field(default_factory=list)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ModerationDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    submission_id: int
    moderator_id: int
    status: ModerationDecisionStatus
    reason: str | None
    decided_at: datetime


def pending_submission_query():
    return (
        select(ListingSubmission)
        .join(Listing, Listing.id == ListingSubmission.listing_id)
        .where(
            Listing.status == ListingStatus.PENDING,
            ~ListingSubmission.decision.has(),
        )
        .options(
            selectinload(ListingSubmission.photos),
            selectinload(ListingSubmission.listing).selectinload(Listing.author),
        )
    )


def _queue_item(submission: ListingSubmission) -> dict:
    return {
        "id": submission.id,
        "listing_id": submission.listing_id,
        "version": submission.version,
        "submitted_at": submission.submitted_at,
        "title": submission.title,
        "price": submission.price,
        "category_name": submission.category_name,
        "category_slug": submission.category_slug,
        "author": submission.listing.author,
        "photos": submission.photos,
    }


@router.get("/queue", response_model=list[ModerationQueueItemResponse])
def moderation_queue(
    session: DatabaseSession,
    moderator: ModeratorUser,
) -> list[dict]:
    del moderator
    statement = pending_submission_query().order_by(
        ListingSubmission.submitted_at, ListingSubmission.id
    )
    submissions = session.scalars(statement).all()
    return [_queue_item(submission) for submission in submissions]


@router.get(
    "/queue/{submission_id}",
    response_model=ModerationQueueDetailResponse,
)
def moderation_queue_detail(
    submission_id: int,
    session: DatabaseSession,
    moderator: ModeratorUser,
) -> dict:
    del moderator
    submission = session.scalar(
        pending_submission_query().where(ListingSubmission.id == submission_id)
    )
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending submission not found",
        )

    result = _queue_item(submission)
    result["description"] = submission.description
    result["rules"] = rule_results(submission.listing, submission.photos)
    return result


@router.get(
    "/queue/{submission_id}/photos/{photo_id}",
    include_in_schema=False,
)
def moderation_submission_photo(
    submission_id: int,
    photo_id: int,
    session: DatabaseSession,
    moderator: ModeratorUser,
) -> FileResponse:
    del moderator
    photo = session.scalar(
        select(ListingSubmissionPhoto)
        .join(ListingSubmission)
        .join(Listing)
        .where(
            ListingSubmission.id == submission_id,
            ListingSubmissionPhoto.id == photo_id,
            Listing.status == ListingStatus.PENDING,
            ~ListingSubmission.decision.has(),
        )
    )
    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending submission photo not found",
        )

    try:
        path = path_for_storage_key(photo.storage_key)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo file not found",
        ) from error
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo file not found",
        )

    return FileResponse(path, media_type=photo.content_type)


@router.post(
    "/queue/{submission_id}/decision",
    response_model=ModerationDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
def decide_submission(
    submission_id: int,
    payload: ModerationDecisionRequest,
    session: DatabaseSession,
    moderator: ModeratorUser,
) -> ModerationDecision:
    submission = session.scalar(
        select(ListingSubmission)
        .options(
            selectinload(ListingSubmission.photos),
            selectinload(ListingSubmission.decision),
            selectinload(ListingSubmission.listing).selectinload(Listing.category),
        )
        .where(ListingSubmission.id == submission_id)
        .with_for_update()
    )
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )

    listing = submission.listing
    if listing.status is not ListingStatus.PENDING or submission.decision is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This submission is no longer pending",
        )
    latest_version = session.scalar(
        select(func.max(ListingSubmission.version)).where(
            ListingSubmission.listing_id == listing.id
        )
    )
    if submission.version != latest_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This submission is no longer the current version",
        )
    if listing.author_id == moderator.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderators cannot decide their own listings",
        )

    if payload.decision is ModerationDecisionStatus.APPROVED:
        expected_rule_ids = {rule.id for rule in RULES}
        if (
            len(payload.confirmed_rule_ids) != len(expected_rule_ids)
            or set(payload.confirmed_rule_ids) != expected_rule_ids
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Confirm every moderation rule before approval",
            )
        violations = validate_listing(listing, submission.photos)
        if violations:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"violations": violations},
            )
    elif not payload.reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A rejection reason is required",
        )

    try:
        decision = record_moderation_decision(
            session,
            submission,
            moderator,
            payload.decision,
            reason=payload.reason,
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This submission has already been decided",
        ) from error
    except ValueError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    session.refresh(decision)
    return decision
