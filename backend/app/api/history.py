from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models import ModerationDecisionStatus
from app.services.history import get_listing_history

router = APIRouter(prefix="/listings", tags=["listing history"])


class SubmissionPhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    storage_key: str
    original_filename: str
    content_type: str
    position: int


class ModerationDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: ModerationDecisionStatus
    reason: str | None
    decided_at: datetime
    moderator_id: int


class ListingSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    submitted_at: datetime
    title: str
    description: str
    price: Decimal
    category_name: str
    category_slug: str
    photos: list[SubmissionPhotoResponse]
    decision: ModerationDecisionResponse | None


@router.get(
    "/{listing_id}/history",
    response_model=list[ListingSubmissionResponse],
)
def listing_history(
    listing_id: int,
    session: DatabaseSession,
    viewer: CurrentUser,
) -> list[ListingSubmissionResponse]:
    try:
        submissions = get_listing_history(session, listing_id, viewer)
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        ) from error
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Listing history is not available to this user",
        ) from error

    return submissions
