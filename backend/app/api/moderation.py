from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import DatabaseSession, ModeratorUser
from app.media_storage import path_for_storage_key
from app.models import (
    Listing,
    ListingStatus,
    ListingSubmission,
    ListingSubmissionPhoto,
)

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


class ModerationQueueDetailResponse(ModerationQueueItemResponse):
    description: str


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
