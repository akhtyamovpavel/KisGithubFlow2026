from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models import Category, Listing, ListingStatus, UserRole
from app.services.history import (
    ListingSubmissionValidationError,
    PhotoSnapshot,
    create_submission,
)
from app.services.listing_validation import RULES, rule_results, validate_listing

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


class ListingViolationResponse(BaseModel):
    rule_id: str
    field: str
    message: str


class ListingRuleResultResponse(BaseModel):
    id: str
    field: str
    label: str
    passed: bool


class ListingRuleResponse(BaseModel):
    id: str
    field: str
    label: str


class ListingValidationResponse(BaseModel):
    valid: bool
    rules: list[ListingRuleResultResponse]
    violations: list[ListingViolationResponse]


def get_owned_listing_for_validation(
    listing_id: int,
    session: DatabaseSession,
    author: CurrentUser,
) -> Listing:
    listing = session.scalar(
        select(Listing)
        .options(selectinload(Listing.category), selectinload(Listing.photos))
        .where(Listing.id == listing_id)
    )
    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )
    if listing.author_id != author.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the listing author can submit this listing",
        )
    return listing


class PublicListingResponse(BaseModel):
    id: int
    title: str
    price: Decimal
    category: str
    main_photo_url: str | None


class PublicListingPhotoResponse(BaseModel):
    id: int
    content_type: str
    position: int


class PublicListingDetailResponse(BaseModel):
    id: int
    title: str
    description: str
    price: Decimal
    category: str
    author_display_name: str
    photos: list[PublicListingPhotoResponse]


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


@router.get("/public/{listing_id}", response_model=PublicListingDetailResponse)
def get_public_listing_detail(
    listing_id: int,
    session: DatabaseSession,
) -> PublicListingDetailResponse:
    statement = (
        select(Listing)
        .where(
            Listing.id == listing_id,
            Listing.status == ListingStatus.PUBLISHED,
        )
        .options(
            selectinload(Listing.category),
            selectinload(Listing.photos),
            selectinload(Listing.author),
        )
    )
    listing = session.scalar(statement)
    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    return PublicListingDetailResponse(
        id=listing.id,
        title=listing.title,
        description=listing.description,
        price=listing.price,
        category=listing.category.name,
        author_display_name=listing.author.display_name,
        photos=[
            PublicListingPhotoResponse(
                id=photo.id,
                content_type=photo.content_type,
                position=photo.position,
            )
            for photo in listing.photos
        ],
    )


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


@router.get("/submission-rules", response_model=list[ListingRuleResponse])
def listing_submission_rules() -> list[ListingRuleResponse]:
    return [
        ListingRuleResponse(id=rule.id, field=rule.field, label=rule.label)
        for rule in RULES
    ]


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


@router.get("/{listing_id}/validation", response_model=ListingValidationResponse)
def validate_listing_for_author(
    listing_id: int,
    session: DatabaseSession,
    author: CurrentUser,
) -> ListingValidationResponse:
    listing = get_owned_listing_for_validation(listing_id, session, author)
    violations = validate_listing(listing)
    rules = rule_results(listing)
    return ListingValidationResponse(
        valid=not violations,
        rules=rules,
        violations=violations,
    )


@router.post("/{listing_id}/submit", response_model=ListingResponse)
def submit_listing(
    listing_id: int,
    session: DatabaseSession,
    author: CurrentUser,
) -> Listing:
    listing = get_owned_listing_for_validation(listing_id, session, author)
    if listing.status not in {ListingStatus.DRAFT, ListingStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only drafts and rejected listings can be submitted",
        )

    photo_snapshots = [
        PhotoSnapshot(
            storage_key=photo.storage_key,
            original_filename=photo.storage_key.rsplit("/", 1)[-1],
            content_type=photo.content_type,
        )
        for photo in listing.photos
    ]
    try:
        create_submission(session, listing, photo_snapshots)
        session.commit()
    except ListingSubmissionValidationError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"violations": error.violations},
        ) from error

    session.refresh(listing)
    return listing


@router.get("", response_model=list[PublicListingResponse])
def list_published_listings(
    session: DatabaseSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[PublicListingResponse]:
    statement = (
        select(Listing)
        .where(Listing.status == ListingStatus.PUBLISHED)
        .options(selectinload(Listing.category), selectinload(Listing.photos))
        .order_by(Listing.published_at.desc(), Listing.id.desc())
    )

    if q is not None:
        normalized_query = q.strip()
        if not normalized_query:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"field": "q", "message": "Search query cannot be empty"},
            )

        escaped_query = (
            normalized_query.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        pattern = f"%{escaped_query}%"
        statement = statement.where(
            or_(
                Listing.title.ilike(pattern, escape="\\"),
                Listing.description.ilike(pattern, escape="\\"),
            )
        )

    if category_id is not None:
        statement = statement.where(
            Listing.category.has(
                Category.id == category_id,
                Category.is_active.is_(True),
            )
        )

    listings = session.scalars(statement).all()
    return [public_listing_response(listing) for listing in listings]
