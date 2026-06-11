"""T066: Domain model Pydantic validation tests for Address."""
from uuid import uuid4

import pytest

from app.domain.customer import Address


def test_address_text_kind() -> None:
    a = Address(kind="text", text_value="Hamra near AUB")
    assert a.kind == "text"
    assert a.text_value == "Hamra near AUB"


def test_address_location_kind() -> None:
    a = Address(kind="location", lat=33.8938, lon=35.5018)
    assert a.kind == "location"
    assert a.lat == pytest.approx(33.8938)
    assert a.lon == pytest.approx(35.5018)


def test_address_invalid_kind_rejected() -> None:
    with pytest.raises(Exception):
        Address(kind="gps")  # type: ignore[arg-type]


def test_address_in_zone_defaults_true() -> None:
    a = Address(kind="text", text_value="Verdun")
    assert a.in_zone is True


def test_address_out_of_zone() -> None:
    a = Address(kind="text", text_value="Remote village", in_zone=False)
    assert a.in_zone is False


def test_address_id_auto_generated() -> None:
    a1 = Address(kind="text", text_value="A")
    a2 = Address(kind="text", text_value="A")
    assert a1.id != a2.id


def test_address_customer_id_optional() -> None:
    cid = uuid4()
    a = Address(kind="text", text_value="Bliss Street", customer_id=cid)
    assert a.customer_id == cid

    b = Address(kind="text", text_value="Bliss Street")
    assert b.customer_id is None


def test_address_area_label_optional() -> None:
    a = Address(kind="text", text_value="Hamra", area_label="Hamra")
    assert a.area_label == "Hamra"

    b = Address(kind="text", text_value="Some unknown place")
    assert b.area_label is None


def test_address_location_no_text() -> None:
    a = Address(kind="location", lat=33.0, lon=35.0)
    assert a.text_value is None
