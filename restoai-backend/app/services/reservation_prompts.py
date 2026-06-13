"""Localized prompt strings for the reservation field-collection flow.

FR-002, FR-003, FR-004, FR-005, FR-020–FR-024.
One constant per collection step; button lists for button-driven steps.
"""
from __future__ import annotations

from app.domain.language import Language
from app.infra.restaurant_info import get_call_center_phone as _get_phone

DATE = {
    Language.EN: "📅 What date would you like to reserve? (e.g., 20 June or 2026-06-20)",
    Language.AR_LB: "📅 شو التاريخ اللي بتريده للحجز؟ (مثلاً: ٢٠ يونيو أو 2026-06-20)",
    Language.ARABIZI: "📅 Shu el date la l7ajez? (Mtal: 20 June aw 2026-06-20)",
}

DATE_PAST = {
    Language.EN: "That date is in the past. Please choose a future date.",
    Language.AR_LB: "هالتاريخ مضى. يرجى اختيار تاريخ مستقبلي.",
    Language.ARABIZI: "Hal ta2rikh fat. Jib ta2rikh tene.",
}

DATE_CONFIRM_TMPL = {
    Language.EN: "📅 I understood the date as *{date_str}*. Is that correct?",
    Language.AR_LB: "📅 فهمت التاريخ كـ *{date_str}*. هل هذا صحيح؟",
    Language.ARABIZI: "📅 Fehmet el ta2rikh: *{date_str}*. Hayda sah?",
}

TIME = {
    Language.EN: "🕐 What time would you like to arrive? (e.g., 7:30 PM)",
    Language.AR_LB: "🕐 شو وقت الوصول؟ (مثلاً: ٧:٣٠ م)",
    Language.ARABIZI: "🕐 Shu wa2et el wusul? (Mtal: 7:30 PM)",
}

PARTY_SIZE = {
    Language.EN: "👥 How many people will be joining?",
    Language.AR_LB: "👥 كم شخص رح يحضر؟",
    Language.ARABIZI: "👥 Adde shi7es ra7 yi7dor?",
}

NAME = {
    Language.EN: "👤 What name should we put the reservation under?",
    Language.AR_LB: "👤 باسم مين رح نحجز؟",
    Language.ARABIZI: "👤 Bismeen ra7 nel7ajez?",
}

PHONE = {
    Language.EN: "📞 What's your phone number for the reservation?",
    Language.AR_LB: "📞 شو رقم هاتفك للحجز؟",
    Language.ARABIZI: "📞 Shu rakam telephonetak la l7ajez?",
}

INDOOR_OUTDOOR = {
    Language.EN: "🪑 Would you prefer indoor or outdoor seating?",
    Language.AR_LB: "🪑 تحب تقعد جوا أو برا؟",
    Language.ARABIZI: "🪑 T7eb to2od jow aw barra?",
}

INDOOR_OUTDOOR_BUTTONS_EN: list[dict[str, str]] = [
    {"label": "🏠 Indoor", "callback_data": "res_seating:indoor"},
    {"label": "🌿 Outdoor", "callback_data": "res_seating:outdoor"},
]
INDOOR_OUTDOOR_BUTTONS_AR: list[dict[str, str]] = [
    {"label": "🏠 جوا", "callback_data": "res_seating:indoor"},
    {"label": "🌿 برا", "callback_data": "res_seating:outdoor"},
]

SMOKING = {
    Language.EN: "🚬 Smoking or non-smoking area?",
    Language.AR_LB: "🚬 قسم التدخين أو عدم التدخين؟",
    Language.ARABIZI: "🚬 Qism el tadkheen aw mish tadkheen?",
}

SMOKING_BUTTONS_EN: list[dict[str, str]] = [
    {"label": "🚬 Smoking", "callback_data": "res_seating:indoor_smoking"},
    {"label": "🚭 Non-Smoking", "callback_data": "res_seating:indoor_non_smoking"},
]
SMOKING_BUTTONS_AR: list[dict[str, str]] = [
    {"label": "🚬 تدخين", "callback_data": "res_seating:indoor_smoking"},
    {"label": "🚭 بدون تدخين", "callback_data": "res_seating:indoor_non_smoking"},
]

TERRACE = {
    Language.EN: "🌿 Outdoor: would you like the terrace?",
    Language.AR_LB: "🌿 برا: تحب التراس؟",
    Language.ARABIZI: "🌿 Barra: t7eb el terrace?",
}

TERRACE_BUTTONS_EN: list[dict[str, str]] = [
    {"label": "🏡 Terrace", "callback_data": "res_seating:outdoor_terrace"},
    {"label": "🌳 Outdoor (non-terrace)", "callback_data": "res_seating:outdoor_non_terrace"},
]
TERRACE_BUTTONS_AR: list[dict[str, str]] = [
    {"label": "🏡 تراس", "callback_data": "res_seating:outdoor_terrace"},
    {"label": "🌳 خارجي بدون تراس", "callback_data": "res_seating:outdoor_non_terrace"},
]

TERRACE_BLOCK = {
    Language.EN: (
        "🚫 Sorry, the terrace seats up to 5 people. "
        "Please choose an alternative:"
    ),
    Language.AR_LB: "🚫 آسف، التراس لأقصى ٥ أشخاص. اختر بديلاً:",
    Language.ARABIZI: "🚫 Sorry, el terrace la 5 ashkhes bass. Ekhtir badel:",
}

TERRACE_REASK_BUTTONS_EN: list[dict[str, str]] = [
    {"label": "🌳 Outdoor (non-terrace)", "callback_data": "res_seating:outdoor_non_terrace"},
    {"label": "🏠 Indoor", "callback_data": "res_seating:indoor"},
]
TERRACE_REASK_BUTTONS_AR: list[dict[str, str]] = [
    {"label": "🌳 خارجي بدون تراس", "callback_data": "res_seating:outdoor_non_terrace"},
    {"label": "🏠 جوا", "callback_data": "res_seating:indoor"},
]

def _build_call_center_redirect() -> dict[Language, str]:
    phone = _get_phone()
    return {
        Language.EN: f"For groups larger than 14, please call our reservations team at {phone}.",
        Language.AR_LB: f"للمجموعات الأكبر من ١٤ شخصاً، يرجى الاتصال على {phone}.",
        Language.ARABIZI: f"La groups akbar min 14, ittasil 3a {phone}.",
    }


CALL_CENTER_REDIRECT = _build_call_center_redirect()
