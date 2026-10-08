from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models import Category, Listing, ListingStatus

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


class ListingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    price: Decimal
    category_id: int
    status: ListingStatus
    created_at: datetime


class PublicListingResponse(BaseModel):
    id: int
    title: str
    price: Decimal
    category: str
    main_photo_url: str | None


def public_listing_response(listing: Listing) -> PublicListingResponse:
    main_photo = min(
        listing.photos,
        key=lambda photo: (photo.position, photo.id),
        default=None,
    )
    return PublicListingResponse(
        id=listing.id,
        title=listing.title,
        price=listing.price,
        category=listing.category.name,
        main_photo_url=f"/media/{main_photo.id}" if main_photo is not None else None,
    )


@router.post(
    "",
    response_model=ListingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_listing(
    payload: ListingCreateRequest,
    session: DatabaseSession,
    author: CurrentUser,
) -> Listing:
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
    return listing


@router.get("/mine", response_model=list[ListingResponse])
def list_my_listings(
    session: DatabaseSession,
    author: CurrentUser,
) -> list[Listing]:
    statement = (
        select(Listing)
        .where(Listing.author_id == author.id)
        .order_by(Listing.created_at.desc(), Listing.id.desc())
    )
    return list(session.scalars(statement).all())


@router.get("", response_model=list[PublicListingResponse])
def list_published_listings(session: DatabaseSession) -> list[PublicListingResponse]:
    statement = (
        select(Listing)
        .where(Listing.status == ListingStatus.PUBLISHED)
        .options(selectinload(Listing.category), selectinload(Listing.photos))
        .order_by(Listing.published_at.desc(), Listing.id.desc())
    )
    listings = session.scalars(statement).all()
    return [public_listing_response(listing) for listing in listings]
