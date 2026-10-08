from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user
from app.config import Settings
from app.database import enable_sqlite_foreign_keys, get_session
from app.main import create_app
from app.models import Base, Category, Listing, ListingStatus, User, UserRole


@pytest.fixture
def listing_client() -> Generator[
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
    user = User(
        email="seller@example.com",
        display_name="Seller",
        password_hash="unused",
        role=UserRole.USER,
    )
    category = Category(name="Books", slug="books", is_active=True)
    session.add_all([user, category])
    session.commit()

    def override_session() -> Generator[Session, None, None]:
        yield session

    application = create_app(Settings(_env_file=None))
    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_current_user] = lambda: user

    with TestClient(application) as client:
        yield client, session, user, category

    session.close()
    engine.dispose()


def listing_payload(category_id: int) -> dict[str, object]:
    return {
        "title": "Film camera",
        "description": "A working film camera in very good condition.",
        "price": "1250.50",
        "category_id": category_id,
    }


def test_create_listing_requires_authentication():
    client = TestClient(create_app(Settings(_env_file=None)))

    response = client.post("/listings", json=listing_payload(1))

    assert response.status_code == 401


def test_create_listing_sets_author_and_draft_status(listing_client):
    client, session, user, category = listing_client

    response = client.post("/listings", json=listing_payload(category.id))

    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    assert response.json()["price"] == "1250.50"

    listing = session.get(Listing, response.json()["id"])
    assert listing is not None
    assert listing.author_id == user.id
    assert listing.status is ListingStatus.DRAFT


def test_create_listing_rejects_inactive_category(listing_client):
    client, session, user, category = listing_client
    category.is_active = False
    session.commit()

    response = client.post("/listings", json=listing_payload(category.id))

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "category_id"


@pytest.mark.parametrize("price", ["-1", "1.001"])
def test_create_listing_rejects_invalid_price(listing_client, price):
    client, _, _, category = listing_client
    payload = listing_payload(category.id)
    payload["price"] = price

    response = client.post("/listings", json=payload)

    assert response.status_code == 422


def test_client_cannot_choose_listing_author_or_status(listing_client):
    client, _, _, category = listing_client
    payload = listing_payload(category.id)
    payload["author_id"] = 987
    payload["status"] = "published"

    response = client.post("/listings", json=payload)

    assert response.status_code == 422


def test_create_listing_rejects_whitespace_only_title(listing_client):
    client, _, _, category = listing_client
    payload = listing_payload(category.id)
    payload["title"] = "   "

    response = client.post("/listings", json=payload)

    assert response.status_code == 422


def test_user_sees_only_own_listings(listing_client):
    client, session, user, category = listing_client
    other_user = User(
        email="other@example.com",
        display_name="Other",
        password_hash="unused",
        role=UserRole.USER,
    )
    session.add(other_user)
    session.flush()
    session.add(
        Listing(
            title="Other item",
            description="An item belonging to another seller.",
            price=Decimal("10.00"),
            category_id=category.id,
            author_id=other_user.id,
            status=ListingStatus.DRAFT,
        )
    )
    session.commit()
    client.post("/listings", json=listing_payload(category.id))

    response = client.get("/listings/mine")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Film camera"]


def test_catalog_combines_category_search_sort_and_pagination(listing_client):
    client, session, user, category = listing_client
    other_category = Category(name="Electronics", slug="electronics", is_active=True)
    inactive_category = Category(name="Archived", slug="archived", is_active=False)
    session.add_all([other_category, inactive_category])
    session.flush()
    matching = []
    for price in ["20.00", "10.00", "30.00"]:
        listing = Listing(
            title="Film camera",
            description="A working film camera in very good condition.",
            price=Decimal(price),
            category_id=category.id,
            author_id=user.id,
            status=ListingStatus.PUBLISHED,
        )
        session.add(listing)
        matching.append(listing)

    for category_id, listing_status in [
        (other_category.id, ListingStatus.PUBLISHED),
        (inactive_category.id, ListingStatus.PUBLISHED),
        (category.id, ListingStatus.DRAFT),
        (category.id, ListingStatus.PENDING),
        (category.id, ListingStatus.REJECTED),
    ]:
        session.add(
            Listing(
                title="Film camera",
                description="A working film camera in very good condition.",
                price=Decimal("1.00"),
                category_id=category_id,
                author_id=user.id,
                status=listing_status,
            )
        )
    session.commit()

    response = client.get(
        "/listings",
        params={
            "q": "camera",
            "category_id": category.id,
            "sort_by": "price",
            "sort_order": "asc",
            "page_size": 1,
            "page": 2,
        },
    )
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3
    assert page["total_pages"] == 3
    assert page["page"] == 2
    assert [item["id"] for item in page["items"]] == [matching[0].id]
    inactive_response = client.get(
        "/listings", params={"category_id": inactive_category.id}
    )
    assert inactive_response.status_code == 200
    assert inactive_response.json()["total"] == 0
