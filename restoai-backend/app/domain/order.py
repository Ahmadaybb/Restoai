from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.domain.customer import Address
from app.domain.language import Language

_DRAFT_TTL_HOURS = 2


class Customization(BaseModel):
    kind: Literal["add", "remove", "cook_pref", "extra_side", "other"]
    text: str = Field(min_length=1)


class OrderItem(BaseModel):
    menu_item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    customizations: list[Customization] = Field(default_factory=list)


class OrderDraft(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    customer_id: UUID
    items: list[OrderItem] = Field(default_factory=list)
    fulfillment: Literal["delivery", "pickup"] | None = None
    address: Address | None = None
    language: Language = Language.EN
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        if self.expires_at is None:
            self.expires_at = self.updated_at + timedelta(hours=_DRAFT_TTL_HOURS)


class OrderState(StrEnum):
    AWAITING_DISPATCHER_REVIEW = "awaiting_dispatcher_review"
    ENTERED_IN_POS = "entered_in_pos"
    CANCELLED = "cancelled"


class ConfirmedOrder(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    customer_id: UUID
    items_snapshot: list[OrderItem]
    fulfillment: Literal["delivery", "pickup"]
    address_snapshot: Address | None = None
    language: Language
    transcript_url: str
    estimated_total_usd: Decimal = Field(ge=Decimal("0"))
    flags: list[Literal["out_of_zone_warning"]] = Field(default_factory=list)
    state: OrderState = OrderState.AWAITING_DISPATCHER_REVIEW
    created_at: datetime = Field(default_factory=datetime.utcnow)
    dispatcher_id: str | None = None
    entered_in_pos_at: datetime | None = None
