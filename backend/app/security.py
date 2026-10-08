from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    secret = settings.auth_secret_key

    if secret is None:
        raise ValueError("MARKETPLACE_AUTH_SECRET_KEY is not configured")

    secret_value = secret.get_secret_value()

    if len(secret_value) < 32:
        raise ValueError("MARKETPLACE_AUTH_SECRET_KEY must be at least 32 characters")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.auth_access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
        "type": "access",
    }
    return jwt.encode(payload, secret_value, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    settings = get_settings()
    secret = settings.auth_secret_key

    if secret is None:
        return None

    secret_value = secret.get_secret_value()

    if len(secret_value) < 32:
        return None

    try:
        payload = jwt.decode(token, secret_value, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None

    if payload.get("type") != "access":
        return None

    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
