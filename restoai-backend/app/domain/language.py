from enum import StrEnum

from pydantic import BaseModel, Field


class Language(StrEnum):
    EN = "en"
    AR_LB = "ar_lb"
    ARABIZI = "arabizi"


class Intent(StrEnum):
    ORDER = "order"
    QUERY = "query"
    RESERVATION = "reservation"
    STATUS = "status"
    IMAGE = "image"
    UNKNOWN = "unknown"


class DetectedLanguage(BaseModel):
    language: Language
    confidence: float = Field(ge=0.0, le=1.0)
