import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Listing,
    ListingPhoto,
    ListingSubmission,
    ListingSubmissionPhoto,
)

logger = logging.getLogger(__name__)


def upload_root() -> Path:
    return get_settings().upload_directory.expanduser().resolve()


def path_for_storage_key(storage_key: str) -> Path:
    root = upload_root()
    path = (root / storage_key).resolve()

    if not path.is_relative_to(root):
        raise ValueError("Invalid media storage key")

    return path


def save_image(listing_id: int, extension: str, content: bytes) -> str:
    storage_key = f"listings/{listing_id}/{uuid4().hex}.{extension}"
    path = path_for_storage_key(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return storage_key


def delete_image(storage_key: str) -> None:
    try:
        path = path_for_storage_key(storage_key)
        path.unlink(missing_ok=True)
        path.parent.rmdir()
    except (OSError, ValueError):
        logger.warning("Could not remove stored listing photo")


def schedule_image_deletion(session: Session, storage_key: str) -> None:
    historical_photo_id = session.scalar(
        select(ListingSubmissionPhoto.id)
        .where(ListingSubmissionPhoto.storage_key == storage_key)
        .limit(1)
    )

    if historical_photo_id is not None:
        return

    pending = session.info.setdefault("listing_photo_cleanup", set())
    pending.add(storage_key)


@event.listens_for(Session, "before_flush")
def schedule_deleted_listing_photos(session, flush_context, instances) -> None:
    pending = session.info.setdefault("listing_photo_cleanup", set())

    for item in session.deleted:
        if isinstance(item, ListingPhoto):
            historical_photo_id = session.connection().execute(
                select(ListingSubmissionPhoto.id)
                .where(ListingSubmissionPhoto.storage_key == item.storage_key)
                .limit(1)
            ).scalar_one_or_none()

            if historical_photo_id is None:
                pending.add(item.storage_key)

        if isinstance(item, Listing):
            photo_statement = select(ListingPhoto.storage_key).where(
                ListingPhoto.listing_id == item.id
            )
            current_keys = session.connection().execute(photo_statement).scalars()
            pending.update(current_keys)

            history_statement = (
                select(ListingSubmissionPhoto.storage_key)
                .join(
                    ListingSubmission,
                    ListingSubmission.id == ListingSubmissionPhoto.submission_id,
                )
                .where(ListingSubmission.listing_id == item.id)
            )
            historical_keys = session.connection().execute(
                history_statement
            ).scalars()
            pending.update(historical_keys)


@event.listens_for(Session, "after_commit")
def delete_committed_listing_photos(session) -> None:
    pending = session.info.pop("listing_photo_cleanup", set())

    for storage_key in pending:
        delete_image(storage_key)


@event.listens_for(Session, "after_rollback")
def clear_rolled_back_listing_photos(session) -> None:
    session.info.pop("listing_photo_cleanup", None)
