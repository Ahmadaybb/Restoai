"""T066: Domain model Pydantic validation tests for Customer."""

import pytest

from app.domain.customer import Customer


def test_customer_valid_phone_e164() -> None:
    c = Customer(phone_e164="+96170123456")
    assert c.phone_e164 == "+96170123456"


def test_customer_phone_must_start_with_plus() -> None:
    with pytest.raises(Exception):
        Customer(phone_e164="96170123456")


def test_customer_phone_too_short() -> None:
    with pytest.raises(Exception):
        Customer(phone_e164="+1234567")  # 7 digits < 8


def test_customer_phone_too_long() -> None:
    with pytest.raises(Exception):
        Customer(phone_e164="+1234567890123456")  # 16 digits > 15


def test_customer_phone_none_is_allowed() -> None:
    c = Customer()
    assert c.phone_e164 is None


def test_customer_display_name_trimmed() -> None:
    c = Customer(display_name="  Ahmad  ")
    assert c.display_name == "Ahmad"


def test_customer_display_name_empty_rejected() -> None:
    with pytest.raises(Exception):
        Customer(display_name="   ")


def test_customer_display_name_too_long_rejected() -> None:
    with pytest.raises(Exception):
        Customer(display_name="A" * 121)


def test_customer_display_name_max_length_accepted() -> None:
    c = Customer(display_name="B" * 120)
    assert len(c.display_name or "") == 120


def test_customer_default_no_addresses() -> None:
    c = Customer()
    assert c.addresses == []


def test_customer_telegram_user_id() -> None:
    c = Customer(telegram_user_id=12345678)
    assert c.telegram_user_id == 12345678


def test_customer_id_auto_generated() -> None:
    c1 = Customer()
    c2 = Customer()
    assert c1.id != c2.id
