from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user, require_moderator
from app.config import Settings
from app.database import enable_sqlite_foreign_keys, get_session
from app.main import create_app
from app.models import (
    Base,
    Category,
    Listing,
    ListingPhoto,
    ListingStatus,
    User,
    UserRole,
)
from app.services.history import (
    ListingSubmissionValidationError,
    create_submission,
)
from app.services.listing_validation import validate_listing


@pytest.fixture
def validation_client() -> Generator[
    tuple[TestClient, Session, User, Category], None, None
]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    session = testing_session()
    author = User(
        email="seller@example.com",
        display_name="Seller",
        password_hash="unused",
        role=UserRole.USER,
    )
    category = Category(name="Books", slug="books", is_active=True)
    session.add_all([author, category])
    session.commit()

    def override_session() -> Generator[Session, None, None]:
        yield session

    application = create_app(Settings(_env_file=None))
    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_current_user] = lambda: author

    with TestClient(application) as client:
        yield client, session, author, category

    session.close()
    engine.dispose()


def payload(category_id: int, *, title: str, description: str) -> dict[str, object]:
    return {
        "title": title,
        "description": description,
        "price": "12.34",
        "category_id": category_id,
    }


@pytest.mark.parametrize(
    ("title", "description", "price", "category_active", "photo_count"),
    [
        ("Book!", "x" * 20, Decimal("0.00"), True, 1),
        ("T" * 120, "x" * 5000, Decimal("9999999999.99"), True, 5),
    ],
)
def test_listing_validation_accepts_rule_boundaries(
    title, description, price, category_active, photo_count
):
    category = Category(
        name="Books", slug="books", is_active=category_active
    )
    listing = Listing(
        title=title,
        description=description,
        price=price,
        category=category,
        photos=[object() for _ in range(photo_count)],
    )

    assert validate_listing(listing) == []


def test_listing_validation_reports_each_field_violation():
    category = Category(name="Books", slug="books", is_active=False)
    listing = Listing(
        title="bad ",
        description="short",
        price=Decimal("-1.001"),
        category=category,
        photos=[object() for _ in range(6)],
    )

    violations = validate_listing(listing)

    assert {item["field"] for item in violations} == {
        "title",
        "description",
        "price",
        "category_id",
        "photos",
    }
    assert {item["rule_id"] for item in violations} == {
        "title_length",
        "description_length",
        "price_precision",
        "active_category",
        "photo_count",
    }


def test_listing_validation_rejects_text_above_maximum_lengths():
    category = Category(name="Books", slug="books", is_active=True)
    listing = Listing(
        title="T" * 121,
        description="x" * 5001,
        price=Decimal("1.00"),
        category=category,
        photos=[object()],
    )

    assert {item["field"] for item in validate_listing(listing)} == {
        "title",
        "description",
    }


def test_listing_validation_rejects_inactive_category_from_api(validation_client):
    client, session, _, category = validation_client
    response = client.post(
        "/listings",
        json=payload(
            category.id,
            title="A book",
            description="A complete description for this book.",
        ),
    )
    category.is_active = False
    session.commit()

    validation = client.get(f"/listings/{response.json()['id']}/validation")

    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert validation.json()["violations"][0]["field"] == "category_id"


def test_rejected_listing_is_validated_again_before_resubmission(validation_client):
    _, session, author, category = validation_client
    listing = Listing(
        title="A book",
        description="A complete description for this book.",
        price=Decimal("10.00"),
        category=category,
        author=author,
        status=ListingStatus.REJECTED,
    )
    session.add(listing)
    session.flush()

    with pytest.raises(ListingSubmissionValidationError) as error:
        create_submission(session, listing, [])

    assert error.value.violations[0]["field"] == "photos"
    assert listing.status is ListingStatus.REJECTED
    assert listing.submissions == []


def test_invalid_listing_does_not_enter_moderation_queue(validation_client):
    client, session, _, category = validation_client
    response = client.post(
        "/listings",
        json=payload(category.id, title="Book", description="Too short"),
    )
    listing_id = response.json()["id"]

    validation = client.get(f"/listings/{listing_id}/validation")
    submission = client.post(f"/listings/{listing_id}/submit")
    listing = session.get(Listing, listing_id)

    moderator = User(
        email="moderator@example.com",
        display_name="Moderator",
        password_hash="unused",
        role=UserRole.MODERATOR,
    )
    session.add(moderator)
    session.commit()
    client.app.dependency_overrides[require_moderator] = lambda: moderator
    queue = client.get("/moderation/queue")

    assert response.status_code == 201
    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert {item["field"] for item in validation.json()["violations"]} == {
        "title",
        "description",
        "photos",
    }
    assert submission.status_code == 422
    assert submission.json()["detail"]["violations"]
    assert listing is not None and listing.status is ListingStatus.DRAFT
    assert queue.status_code == 200
    assert queue.json() == []


def test_valid_listing_submission_is_snapshotted_and_queued(validation_client):
    client, session, _, category = validation_client
    response = client.post(
        "/listings",
        json=payload(
            category.id,
            title="A book",
            description="A well-kept book for a new reader.",
        ),
    )
    listing_id = response.json()["id"]
    session.add(
        ListingPhoto(
            listing_id=listing_id,
            storage_key=f"listings/{listing_id}/cover.jpg",
            content_type="image/jpeg",
            position=0,
        )
    )
    session.commit()

    validation = client.get(f"/listings/{listing_id}/validation")
    submission = client.post(f"/listings/{listing_id}/submit")
    listing = session.get(Listing, listing_id)
    moderator = User(
        email="moderator@example.com",
        display_name="Moderator",
        password_hash="unused",
        role=UserRole.MODERATOR,
    )
    session.add(moderator)
    session.commit()
    client.app.dependency_overrides[require_moderator] = lambda: moderator
    queue = client.get("/moderation/queue")

    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert submission.status_code == 200
    assert submission.json()["status"] == "pending"
    assert listing is not None and listing.status is ListingStatus.PENDING
    assert queue.status_code == 200
    assert len(queue.json()) == 1
    assert queue.json()[0]["photos"][0]["original_filename"] == "cover.jpg"
