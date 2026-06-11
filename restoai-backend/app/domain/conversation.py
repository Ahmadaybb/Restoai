from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.domain.language import Intent, Language


class Turn(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    sender: Literal["customer", "bot", "dispatcher"]
    text: str
    language: Language
    intent: Intent | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Conversation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    customer_id: UUID
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)
    awaiting_human: bool = False
    assigned_dispatcher_id: str | None = None
    active_draft_id: UUID | None = None


class FailureCounter(BaseModel):
    customer_id: UUID
    field: Literal["order_parse", "dish_match", "address_extract"]
    count: int = Field(ge=0, default=0)
