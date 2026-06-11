from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MenuItem(BaseModel):
    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    name_ar: str = Field(min_length=1)
    name_translit: str | None = None
    description_en: str | None = None
    description_ar: str | None = None
    price_usd: Decimal = Field(ge=Decimal("0"))
    available: bool = True
    spice_level: Literal["none", "mild", "medium", "spicy"] | None = None
    tags: list[str] = Field(default_factory=list)


class MenuChunk(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    menu_item_id: str
    text: str = Field(min_length=1)
    language: Literal["en", "ar"]
    embedding: list[float] | None = None
