from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, DatabaseSession, OptionalCurrentUser
from app.images import InvalidImageError, sanitize_image
from app.media_storage import (
    delete_image,
    path_for_storage_key,
    save_image,
    schedule_image_deletion,
)
from app.models import Listing, ListingPhoto, ListingStatus, UserRole, utc_now

router = APIRouter(tags=["listing photos"])
MAX_PHOTO_COUNT = 5
MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024


class ListingPhotoResponse(BaseModel):
    id: int
    url: str
    content_type: str
    position: int


def get_owned_listing(
    session: DatabaseSession,
    listing_id: int,
    user: CurrentUser,
) -> Listing:
    listing = session.get(Listing, listing_id)

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    if listing.author_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the listing author can manage its photos",
        )

    return listing


def get_editable_listing(
    session: DatabaseSession,
    listing_id: int,
    user: CurrentUser,
) -> Listing:
    listing = get_owned_listing(session, listing_id, user)
    if listing.status not in {ListingStatus.DRAFT, ListingStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only drafts and rejected listings can be edited",
        )
    return listing


def photo_response(photo: ListingPhoto) -> ListingPhotoResponse:
    return ListingPhotoResponse(
        id=photo.id,
        url=f"/media/{photo.id}",
        content_type=photo.content_type,
        position=photo.position,
    )


async def read_valid_image(image: UploadFile) -> tuple[bytes, str, str]:
    if image.size is not None and image.size > MAX_PHOTO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Each photo must be no larger than 5 MB",
        )

    content = await image.read(MAX_PHOTO_SIZE_BYTES + 1)

    if len(content) > MAX_PHOTO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Each photo must be no larger than 5 MB",
        )

    try:
        return await run_in_threadpool(sanitize_image, content)
    except InvalidImageError as error:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(error),
        ) from error


def get_next_position(session: DatabaseSession, listing_id: int) -> int:
    positions = set(
        session.scalars(
            select(ListingPhoto.position).where(
                ListingPhoto.listing_id == listing_id
            )
        ).all()
    )

    for position in range(MAX_PHOTO_COUNT):
        if position not in positions:
            return position

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="An ad can have no more than 5 photos",
    )


@router.get(
    "/listings/{listing_id}/photos",
    response_model=list[ListingPhotoResponse],
)
def list_listing_photos(
    listing_id: int,
    session: DatabaseSession,
    user: CurrentUser,
) -> list[ListingPhotoResponse]:
    get_owned_listing(session, listing_id, user)
    photos = session.scalars(
        select(ListingPhoto)
        .where(ListingPhoto.listing_id == listing_id)
        .order_by(ListingPhoto.position, ListingPhoto.id)
    ).all()
    return [photo_response(photo) for photo in photos]


@router.post(
    "/listings/{listing_id}/photos",
    response_model=ListingPhotoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_listing_photo(
    listing_id: int,
    session: DatabaseSession,
    user: CurrentUser,
    image: Annotated[UploadFile, File()],
) -> ListingPhotoResponse:
    listing = get_editable_listing(session, listing_id, user)
    photo_count = session.scalar(
        select(func.count(ListingPhoto.id)).where(
            ListingPhoto.listing_id == listing.id
        )
    )

    if photo_count >= MAX_PHOTO_COUNT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An ad can have no more than 5 photos",
        )

    content, content_type, extension = await read_valid_image(image)
    storage_key = save_image(listing.id, extension, content)
    photo = ListingPhoto(
        listing_id=listing.id,
        storage_key=storage_key,
        content_type=content_type,
        position=get_next_position(session, listing.id),
    )
    session.add(photo)
    listing.updated_at = utc_now()

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        delete_image(storage_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An ad can have no more than 5 photos",
        ) from error

    session.refresh(photo)
    return photo_response(photo)


@router.put(
    "/listings/{listing_id}/photos/{photo_id}",
    response_model=ListingPhotoResponse,
)
async def replace_listing_photo(
    listing_id: int,
    photo_id: int,
    session: DatabaseSession,
    user: CurrentUser,
    image: Annotated[UploadFile, File()],
) -> ListingPhotoResponse:
    listing = get_editable_listing(session, listing_id, user)
    photo = session.get(ListingPhoto, photo_id)

    if photo is None or photo.listing_id != listing.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    content, content_type, extension = await read_valid_image(image)
    old_storage_key = photo.storage_key
    new_storage_key = save_image(listing.id, extension, content)
    photo.storage_key = new_storage_key
    photo.content_type = content_type
    listing.updated_at = utc_now()
    schedule_image_deletion(session, old_storage_key)

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        delete_image(new_storage_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Photo could not be replaced",
        ) from error

    session.refresh(photo)
    return photo_response(photo)


@router.delete(
    "/listings/{listing_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_listing_photo(
    listing_id: int,
    photo_id: int,
    session: DatabaseSession,
    user: CurrentUser,
) -> None:
    listing = get_editable_listing(session, listing_id, user)
    photo = session.get(ListingPhoto, photo_id)

    if photo is None or photo.listing_id != listing.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    session.delete(photo)
    listing.updated_at = utc_now()
    session.commit()


@router.get("/media/{photo_id}", include_in_schema=False)
def get_photo_file(
    photo_id: int,
    session: DatabaseSession,
    user: OptionalCurrentUser,
) -> FileResponse:
    photo = session.get(ListingPhoto, photo_id)

    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    listing = session.get(Listing, photo.listing_id)

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    if listing.status != ListingStatus.PUBLISHED:
        can_view_private_photo = (
            user is not None
            and (
                user.id == listing.author_id
                or user.role == UserRole.MODERATOR
            )
        )

        if not can_view_private_photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo not found",
            )

    path = path_for_storage_key(photo.storage_key)

    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo file not found",
        )

    return FileResponse(path, media_type=photo.content_type)
