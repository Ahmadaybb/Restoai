"""Pydantic input/output models for every internal LLM-callable tool."""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.language import Language
from app.domain.order import OrderDraft, OrderItem

# ── parse_order ──────────────────────────────────────────────────────────────

class ParseOrderIn(BaseModel):
    text: str
    language: Language


class ParseOrderOut(BaseModel):
    items: list[OrderItem] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


# ── match_dish ────────────────────────────────────────────────────────────────

class DishAlternative(BaseModel):
    menu_item_id: str
    score: float = Field(ge=0.0, le=1.0)


class MatchDishIn(BaseModel):
    phrase: str
    language: Language


class MatchDishOut(BaseModel):
    menu_item_id: str | None = None
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    alternatives: list[DishAlternative] = Field(default_factory=list)


# ── answer_menu_question ──────────────────────────────────────────────────────

class MenuCitation(BaseModel):
    menu_item_id: str
    chunk_id: UUID


class AnswerMenuQuestionIn(BaseModel):
    question: str
    language: Language


class AnswerMenuQuestionOut(BaseModel):
    answer: str
    citations: list[MenuCitation] = Field(default_factory=list)


# ── extract_address ───────────────────────────────────────────────────────────

class ExtractAddressIn(BaseModel):
    text: str
    language: Language


class ExtractAddressOut(BaseModel):
    kind: Literal["text", "location"]
    text_value: str | None = None
    lat: float | None = None
    lon: float | None = None
    area_label: str | None = None
    area_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


# ── check_zone ────────────────────────────────────────────────────────────────

class CheckZoneIn(BaseModel):
    area_label: str | None = None


class CheckZoneOut(BaseModel):
    in_zone: bool
    matched_entry: str | None = None


# ── detect_language ───────────────────────────────────────────────────────────

class DetectLanguageIn(BaseModel):
    text: str


class DetectLanguageOut(BaseModel):
    language: Language
    confidence: float = Field(ge=0.0, le=1.0)


# ── render_readback ───────────────────────────────────────────────────────────

class ReadbackButton(BaseModel):
    label: str
    callback_data: str


class RenderReadbackIn(BaseModel):
    draft: OrderDraft
    language: Language


class RenderReadbackOut(BaseModel):
    text: str
    buttons: list[ReadbackButton] = Field(default_factory=list)


# ── summarize_for_dispatcher ──────────────────────────────────────────────────

class SummarizeForDispatcherIn(BaseModel):
    transcript: list[Any] = Field(default_factory=list)  # list[Turn]
    draft: OrderDraft | None = None


class SummarizeForDispatcherOut(BaseModel):
    summary: str
