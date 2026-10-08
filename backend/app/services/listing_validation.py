from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.models import Listing


@dataclass(frozen=True)
class ListingRule:
    id: str
    field: str
    label: str


RULES = (
    ListingRule("title_length", "title", "Заголовок: от 5 до 120 символов"),
    ListingRule(
        "description_length", "description", "Описание: от 20 до 5000 символов"
    ),
    ListingRule(
        "price_precision",
        "price",
        "Цена: неотрицательная, не более двух знаков после запятой",
    ),
    ListingRule("active_category", "category_id", "Выбрана действующая категория"),
    ListingRule("photo_count", "photos", "Добавлено от 1 до 5 фотографий"),
)


def validate_listing(
    listing: Listing,
    photos: list[Any] | None = None,
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    title_length = len(listing.title.strip())
    description_length = len(listing.description.strip())
    price = Decimal(listing.price)
    photo_count = len(listing.photos if photos is None else photos)
    category = listing.category

    if not 5 <= title_length <= 120:
        violations.append(
            {
                "rule_id": "title_length",
                "field": "title",
                "message": "Укажите заголовок длиной от 5 до 120 символов.",
            }
        )
    if not 20 <= description_length <= 5000:
        violations.append(
            {
                "rule_id": "description_length",
                "field": "description",
                "message": "Укажите описание длиной от 20 до 5000 символов.",
            }
        )
    if not price.is_finite() or price < 0 or price.as_tuple().exponent < -2:
        violations.append(
            {
                "rule_id": "price_precision",
                "field": "price",
                "message": (
                    "Укажите неотрицательную цену с точностью до двух знаков "
                    "после запятой."
                ),
            }
        )
    if category is None or not category.is_active:
        violations.append(
            {
                "rule_id": "active_category",
                "field": "category_id",
                "message": "Выберите действующую категорию.",
            }
        )
    if not 1 <= photo_count <= 5:
        violations.append(
            {
                "rule_id": "photo_count",
                "field": "photos",
                "message": "Добавьте от 1 до 5 фотографий.",
            }
        )

    return violations


def rule_results(
    listing: Listing,
    photos: list[Any] | None = None,
) -> list[dict[str, str | bool]]:
    failed_rule_ids = {item["rule_id"] for item in validate_listing(listing, photos)}
    return [
        {
            "id": rule.id,
            "field": rule.field,
            "label": rule.label,
            "passed": rule.id not in failed_rule_ids,
        }
        for rule in RULES
    ]
