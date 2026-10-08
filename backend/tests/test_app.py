import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("MARKETPLACE_APP_NAME", raising=False)
    monkeypatch.delenv("MARKETPLACE_CORS_ORIGINS", raising=False)
    settings = Settings(_env_file=None)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_returns_service_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_and_openapi_are_available(client):
    response = client.get("/docs")
    schema = client.get("/openapi.json")

    assert response.status_code == 200
    assert schema.status_code == 200
    assert "/health" in schema.json()["paths"]


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
def test_vite_origins_receive_cors_headers(client, origin):
    response = client.get("/health", headers={"Origin": origin})
    preflight = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    assert response.headers["access-control-allow-origin"] == origin
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin


def test_unlisted_origin_is_not_allowed(client):
    origin = "https://unlisted.example"
    response = client.get("/health", headers={"Origin": origin})
    preflight = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


def test_environment_configures_application(monkeypatch):
    monkeypatch.setenv("MARKETPLACE_APP_NAME", "Configured Marketplace")
    monkeypatch.setenv("MARKETPLACE_CORS_ORIGINS", '["https://catalog.example"]')
    settings = Settings(_env_file=None)

    with TestClient(create_app(settings)) as client:
        schema = client.get("/openapi.json").json()
        response = client.get(
            "/health", headers={"Origin": "https://catalog.example"}
        )

    assert schema["info"]["title"] == "Configured Marketplace"
    assert response.headers["access-control-allow-origin"] == "https://catalog.example"


def test_environment_takes_precedence_over_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_values = [
        'MARKETPLACE_APP_NAME="Name from dotenv"',
        'MARKETPLACE_CORS_ORIGINS=\'["https://dotenv.example"]\'',
    ]
    env_file.write_text("\n".join(env_values), encoding="utf-8")
    monkeypatch.setenv("MARKETPLACE_APP_NAME", "Name from environment")
    monkeypatch.delenv("MARKETPLACE_CORS_ORIGINS", raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "Name from environment"
    assert settings.cors_origins == ["https://dotenv.example"]
