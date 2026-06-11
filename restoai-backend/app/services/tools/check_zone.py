"""check_zone tool — FR-035.

Pure function: rapidfuzz token-set ratio against the zone list.
Threshold >= 80; below threshold → not confident, don't warn (R8).
"""
from rapidfuzz import fuzz, process

from app.domain.tools import CheckZoneIn, CheckZoneOut
from app.repositories.zone_repo import list_areas

_MATCH_THRESHOLD = 80


def check_zone(inp: CheckZoneIn) -> CheckZoneOut:
    if inp.area_label is None:
        return CheckZoneOut(in_zone=True, matched_entry=None)

    areas = list_areas()
    if not areas:
        return CheckZoneOut(in_zone=True, matched_entry=None)

    result = process.extractOne(
        inp.area_label,
        areas,
        scorer=fuzz.token_set_ratio,
    )
    if result is None or result[1] < _MATCH_THRESHOLD:
        return CheckZoneOut(in_zone=False, matched_entry=None)

    return CheckZoneOut(in_zone=True, matched_entry=result[0])
