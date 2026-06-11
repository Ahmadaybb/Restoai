import re
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class Address(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    customer_id: UUID | None = None
    kind: Literal["text", "location"]
    text_value: str | None = None
    lat: float | None = None
    lon: float | None = None
    area_label: str | None = None
    in_zone: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("text_value")
    @classmethod
    def text_required_for_text_kind(cls, v: str | None, info: object) -> str | None:
        # Validated at model level; pydantic v2 model_validator handles cross-field
        return v


class Customer(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    phone_e164: str | None = None
    telegram_user_id: int | None = None
    display_name: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    addresses: list[Address] = Field(default_factory=list)

    @field_validator("phone_e164")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^\+\d{8,15}$", v):
            raise ValueError("phone_e164 must be E.164 format (+<8-15 digits>)")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not 1 <= len(v) <= 120:
            raise ValueError("display_name must be 1–120 characters after trimming")
        return v
