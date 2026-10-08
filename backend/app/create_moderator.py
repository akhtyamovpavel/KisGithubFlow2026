from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def main() -> None:
    settings = get_settings()

    if (
        settings.moderator_email is None
        or settings.moderator_display_name is None
        or settings.moderator_password is None
    ):
        raise SystemExit(
            "Set MARKETPLACE_MODERATOR_EMAIL, "
            "MARKETPLACE_MODERATOR_DISPLAY_NAME and "
            "MARKETPLACE_MODERATOR_PASSWORD first"
        )

    try:
        email = TypeAdapter(EmailStr).validate_python(settings.moderator_email)
    except ValidationError as error:
        raise SystemExit("MARKETPLACE_MODERATOR_EMAIL must be a valid email") from error

    display_name = settings.moderator_display_name.strip()
    password = settings.moderator_password.get_secret_value()

    if not display_name:
        raise SystemExit("MARKETPLACE_MODERATOR_DISPLAY_NAME cannot be empty")

    if len(password) < 12 or len(password) > 128:
        raise SystemExit(
            "MARKETPLACE_MODERATOR_PASSWORD must contain 12 to 128 characters"
        )

    normalized_email = str(email).strip().casefold()

    with SessionLocal() as session:
        moderator_exists = session.scalar(
            select(User.id).where(User.role == UserRole.MODERATOR)
        )

        if moderator_exists is not None:
            raise SystemExit("A moderator account already exists")

        user = session.scalar(select(User).where(User.email == normalized_email))

        if user is None:
            user = User(
                email=normalized_email,
                display_name=display_name,
                password_hash=hash_password(password),
                role=UserRole.MODERATOR,
            )
            session.add(user)
        else:
            user.display_name = display_name
            user.password_hash = hash_password(password)
            user.role = UserRole.MODERATOR

        session.commit()

    print(f"Moderator account ready: {normalized_email}")


if __name__ == "__main__":
    main()
