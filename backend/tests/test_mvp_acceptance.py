from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_session
from app.config import Settings, get_settings
from app.database import enable_sqlite_foreign_keys
from app.main import create_app
from app.models import Base, Category, User, UserRole
from app.security import hash_password


@pytest.fixture
def marketplace_client(
    tmp_path, monkeypatch
) -> Generator[tuple[TestClient, Session, Category], None, None]:
    monkeypatch.setenv(
        "MARKETPLACE_AUTH_SECRET_KEY",
        "acceptance-test-secret-that-is-at-least-32-characters",
    )
    get_settings.cache_clear()
    monkeypatch.setattr("app.media_storage.upload_root", lambda: tmp_path)

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
    category = Category(name="Фотоаппараты", slug="cameras", is_active=True)
    moderator = User(
        email="moderator@example.com",
        display_name="Модератор",
        password_hash=hash_password("Moderator-password-2026"),
        role=UserRole.MODERATOR,
    )
    session.add_all([category, moderator])
    session.commit()

    def override_session() -> Generator[Session, None, None]:
        yield session

    application = create_app(Settings(_env_file=None, upload_directory=tmp_path))
    application.dependency_overrides[get_session] = override_session
    with TestClient(application) as client:
        yield client, session, category

    session.close()
    engine.dispose()
    get_settings.cache_clear()


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def png_image() -> bytes:
    image = Image.new("RGB", (2, 2), color="navy")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_author_moderation_resubmission_and_publication(marketplace_client):
    client, session, category = marketplace_client

    registration = client.post(
        "/auth/register",
        json={
            "email": "author@example.com",
            "display_name": "Автор",
            "password": "Author-password-2026",
        },
    )
    assert registration.status_code == 201
    assert registration.json()["role"] == "user"
    author_token = login(client, "author@example.com", "Author-password-2026")
    moderator_token = login(
        client, "moderator@example.com", "Moderator-password-2026"
    )
    author_headers = authorization(author_token)
    moderator_headers = authorization(moderator_token)

    created = client.post(
        "/listings",
        headers=author_headers,
        json={
            "title": "Плёночный фотоаппарат",
            "description": "Рабочий фотоаппарат в хорошем состоянии.",
            "price": "1250.00",
            "category_id": category.id,
        },
    )
    assert created.status_code == 201
    listing_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    uploaded = client.post(
        f"/listings/{listing_id}/photos",
        headers=author_headers,
        files={"image": ("camera.png", png_image(), "image/png")},
    )
    assert uploaded.status_code == 201
    photo_id = uploaded.json()["id"]
    assert client.get(f"/media/{photo_id}").status_code == 404
    assert client.get("/listings").json()["items"] == []

    first_submission = client.post(
        f"/listings/{listing_id}/submit", headers=author_headers
    )
    assert first_submission.status_code == 200
    assert first_submission.json()["status"] == "pending"
    queue = client.get("/moderation/queue", headers=moderator_headers)
    assert queue.status_code == 200
    assert len(queue.json()) == 1
    first_submission_id = queue.json()[0]["id"]
    assert queue.json()[0]["version"] == 1
    assert client.get("/listings").json()["items"] == []
    assert client.get(f"/media/{photo_id}").status_code == 404

    missing_reason = client.post(
        f"/moderation/queue/{first_submission_id}/decision",
        headers=moderator_headers,
        json={"decision": "rejected", "reason": "  "},
    )
    assert missing_reason.status_code == 422
    rejected = client.post(
        f"/moderation/queue/{first_submission_id}/decision",
        headers=moderator_headers,
        json={
            "decision": "rejected",
            "reason": "Укажите состояние корпуса и комплектность.",
        },
    )
    assert rejected.status_code == 201
    assert rejected.json()["status"] == "rejected"
    assert client.get(f"/listings/{listing_id}", headers=author_headers).json()[
        "status"
    ] == "rejected"
    assert client.get("/listings").json()["items"] == []
    assert client.get(f"/media/{photo_id}").status_code == 404

    correction = client.put(
        f"/listings/{listing_id}",
        headers=author_headers,
        json={
            "title": "Плёночный фотоаппарат",
            "description": (
                "Рабочий фотоаппарат: корпус в хорошем состоянии, в комплекте "
                "ремень и крышка объектива."
            ),
            "price": "1250.00",
            "category_id": category.id,
        },
    )
    assert correction.status_code == 200
    assert correction.json()["status"] == "rejected"

    second_submission = client.post(
        f"/listings/{listing_id}/submit", headers=author_headers
    )
    assert second_submission.status_code == 200
    assert second_submission.json()["status"] == "pending"
    assert client.post(
        f"/listings/{listing_id}/submit", headers=author_headers
    ).status_code == 409
    assert client.get("/listings").json()["items"] == []
    assert client.get(f"/media/{photo_id}").status_code == 404

    pending_queue = client.get("/moderation/queue", headers=moderator_headers)
    assert pending_queue.status_code == 200
    assert len(pending_queue.json()) == 1
    second_submission_id = pending_queue.json()[0]["id"]
    assert pending_queue.json()[0]["version"] == 2
    incomplete_approval = client.post(
        f"/moderation/queue/{second_submission_id}/decision",
        headers=moderator_headers,
        json={"decision": "approved"},
    )
    assert incomplete_approval.status_code == 422
    assert client.get("/listings").json()["items"] == []

    approved = client.post(
        f"/moderation/queue/{second_submission_id}/decision",
        headers=moderator_headers,
        json={
            "decision": "approved",
            "confirmed_rule_ids": [
                "title_length",
                "description_length",
                "price_precision",
                "active_category",
                "photo_count",
            ],
        },
    )
    assert approved.status_code == 201
    assert approved.json()["status"] == "approved"
    assert client.get(f"/listings/{listing_id}", headers=author_headers).json()[
        "status"
    ] == "published"
    catalog = client.get("/listings").json()
    assert [item["id"] for item in catalog["items"]] == [listing_id]
    assert client.get(f"/media/{photo_id}").status_code == 200
    assert client.get(f"/listings/public/{listing_id}").status_code == 200

    history = client.get(
        f"/listings/{listing_id}/history", headers=author_headers
    )
    assert history.status_code == 200
    assert [submission["version"] for submission in history.json()] == [1, 2]
    first, second = history.json()
    assert first["description"] == "Рабочий фотоаппарат в хорошем состоянии."
    assert first["decision"]["status"] == "rejected"
    assert first["decision"]["reason"] == "Укажите состояние корпуса и комплектность."
    assert first["photos"][0]["content_type"] == "image/png"
    assert "состояние" in second["description"]
    assert second["decision"]["status"] == "approved"
    assert second["decision"]["moderator_id"] == session.query(User).filter_by(
        email="moderator@example.com"
    ).one().id
