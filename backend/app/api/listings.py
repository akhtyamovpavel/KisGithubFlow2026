from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models import Category, Listing, ListingStatus, UserRole

router = APIRouter(prefix="/listings", tags=["listings"])


class ListingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    category_id: int = Field(gt=0)

    @field_validator("title", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError("This field cannot be empty")

        return normalized_value


class ListingUpdateRequest(ListingCreateRequest):
    pass


class ListingPhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_type: str
    position: int


class ListingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    price: Decimal
    category_id: int
    status: ListingStatus
    created_at: datetime
    updated_at: datetime
    photos: list[ListingPhotoResponse]


def listing_response(listing: Listing) -> dict:
    return {
        "id": listing.id,
        "title": listing.title,
        "description": listing.description,
        "price": listing.price,
        "category_id": listing.category_id,
        "status": listing.status,
        "created_at": listing.created_at,
        "updated_at": listing.updated_at,
        "photos": listing.photos,
    }


def get_listing_for_view(
    session: DatabaseSession,
    listing_id: int,
    viewer: CurrentUser,
) -> Listing:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )
    if listing.author_id != viewer.id and viewer.role is not UserRole.MODERATOR:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )
    return listing


def get_listing_for_edit(
    session: DatabaseSession,
    listing_id: int,
    author: CurrentUser,
) -> Listing:
    listing = session.get(Listing, listing_id)
    if listing is None or listing.author_id != author.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )
    if listing.status not in {ListingStatus.DRAFT, ListingStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only drafts and rejected listings can be edited",
        )
    return listing


@router.post(
    "",
    response_model=ListingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_listing(
    payload: ListingCreateRequest,
    session: DatabaseSession,
    author: CurrentUser,
) -> dict:
    category = session.scalar(
        select(Category).where(
            Category.id == payload.category_id,
            Category.is_active.is_(True),
        )
    )

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "field": "category_id",
                "message": "Select an active category",
            },
        )

    listing = Listing(
        title=payload.title.strip(),
        description=payload.description.strip(),
        price=payload.price,
        category_id=category.id,
        author_id=author.id,
        status=ListingStatus.DRAFT,
    )
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing_response(listing)


@router.get("/mine", response_model=list[ListingResponse])
def list_my_listings(
    session: DatabaseSession,
    author: CurrentUser,
) -> list[dict]:
    statement = (
        select(Listing)
        .where(Listing.author_id == author.id)
        .order_by(Listing.created_at.desc(), Listing.id.desc())
    )
    listings = session.scalars(statement).all()
    return [listing_response(listing) for listing in listings]


@router.get("/{listing_id}", response_model=ListingResponse)
def get_listing(
    listing_id: int,
    session: DatabaseSession,
    viewer: CurrentUser,
) -> dict:
    return listing_response(get_listing_for_view(session, listing_id, viewer))


@router.put("/{listing_id}", response_model=ListingResponse)
def update_draft_listing(
    listing_id: int,
    payload: ListingUpdateRequest,
    session: DatabaseSession,
    author: CurrentUser,
) -> dict:
    listing = get_listing_for_edit(session, listing_id, author)
    category = session.scalar(
        select(Category).where(
            Category.id == payload.category_id,
            Category.is_active.is_(True),
        )
    )
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"field": "category_id", "message": "Select an active category"},
        )

    listing.title = payload.title
    listing.description = payload.description
    listing.price = payload.price
    listing.category_id = category.id
    session.commit()
    session.refresh(listing)
    return listing_response(listing)
