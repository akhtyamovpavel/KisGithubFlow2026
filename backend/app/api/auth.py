from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, DatabaseSession
from app.config import get_settings
from app.models import User, UserRole
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])


class RegistrationRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError("Display name cannot be empty")

        return normalized_value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    role: UserRole


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def normalize_email(email: str) -> str:
    return email.strip().casefold()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    payload: RegistrationRequest,
    session: DatabaseSession,
) -> User:
    email = normalize_email(str(payload.email))
    existing_user = session.scalar(select(User).where(User.email == email))

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=UserRole.USER,
    )
    session.add(user)

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from error

    session.refresh(user)
    return user


@router.post("/login", response_model=AccessTokenResponse)
def login(
    payload: LoginRequest,
    session: DatabaseSession,
) -> AccessTokenResponse:
    email = normalize_email(str(payload.email))
    user = session.scalar(select(User).where(User.email == email))

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = create_access_token(user.id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        ) from error

    settings = get_settings()
    return AccessTokenResponse(
        access_token=token,
        expires_in=settings.auth_access_token_ttl_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
def current_user(user: CurrentUser) -> User:
    return user
