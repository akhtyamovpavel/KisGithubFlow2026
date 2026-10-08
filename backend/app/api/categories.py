from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.models import Category

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


@router.get("", response_model=list[CategoryResponse])
def list_categories(session: DatabaseSession) -> list[Category]:
    statement = (
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.name, Category.id)
    )
    return list(session.scalars(statement).all())
