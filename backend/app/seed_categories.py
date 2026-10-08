from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Category

INITIAL_CATEGORIES = (
    ("Транспорт", "vehicles"),
    ("Недвижимость", "real-estate"),
    ("Электроника", "electronics"),
    ("Дом и сад", "home-and-garden"),
    ("Одежда и обувь", "clothing-and-shoes"),
    ("Детские товары", "children"),
    ("Хобби и спорт", "hobbies-and-sports"),
    ("Услуги", "services"),
    ("Другое", "other"),
)


def seed_categories(session: Session) -> int:
    existing_slugs = set(session.scalars(select(Category.slug)).all())
    inserted_count = 0

    for name, slug in INITIAL_CATEGORIES:
        if slug in existing_slugs:
            continue

        session.add(Category(name=name, slug=slug, is_active=True))
        inserted_count += 1

    session.commit()
    return inserted_count


def main() -> None:
    with SessionLocal() as session:
        inserted_count = seed_categories(session)

    message = f"Добавлено категорий: {inserted_count}"
    print(message)


if __name__ == "__main__":
    main()
