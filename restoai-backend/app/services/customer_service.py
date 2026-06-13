"""CustomerService — customer recognition and profile management.

FR-012, FR-014: find returning customers by phone; create new profiles
on first confirmed order.
"""
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customer import Address, Customer
from app.repositories import customer_repo

logger = logging.getLogger(__name__)


async def find_by_phone_e164(
    session: AsyncSession, phone: str
) -> Customer | None:
    return await customer_repo.find_by_phone_e164(session, phone)


async def find_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> Customer | None:
    return await customer_repo.find_by_telegram_id(session, telegram_id)


async def get_or_create_anonymous(
    session: AsyncSession, telegram_id: int
) -> Customer:
    """Return existing customer by Telegram id or create a new anonymous one."""
    customer = await customer_repo.find_by_telegram_id(session, telegram_id)
    if customer is None:
        customer = Customer(telegram_user_id=telegram_id)
        customer = await customer_repo.create(session, customer)
        await session.commit()
        logger.info("customer_created_anonymous", extra={"telegram_id": telegram_id})
    return customer


async def bind_phone_from_contact(
    session: AsyncSession,
    customer_id: UUID,
    phone_e164: str,
) -> Customer:
    """FR-014: Bind a Telegram-shared phone to the customer record."""
    await customer_repo.update_fields(
        session, customer_id, phone_e164=phone_e164
    )
    await session.commit()
    customer = Customer(id=customer_id, phone_e164=phone_e164)
    logger.info("customer_phone_bound", extra={"customer_id": str(customer_id)})
    return customer


async def set_display_name(
    session: AsyncSession, customer_id: UUID, name: str
) -> None:
    await customer_repo.update_fields(
        session, customer_id, display_name=name.strip()[:120]
    )
    await session.commit()


async def persist_on_confirmation(
    session: AsyncSession,
    customer: Customer,
    address: Address | None = None,
) -> None:
    """FR-014: Persist phone/name/address on first confirmation."""
    updates = {}
    if customer.phone_e164:
        updates["phone_e164"] = customer.phone_e164
    if customer.display_name:
        updates["display_name"] = customer.display_name
    if updates:
        await customer_repo.update_fields(session, customer.id, **updates)
    if address is not None and customer.phone_e164:
        address_with_customer = address.model_copy(
            update={"customer_id": customer.id}
        )
        await customer_repo.save_address(session, address_with_customer)
    await session.commit()


async def update_last_seen(
    session: AsyncSession, customer_id: UUID
) -> None:
    await customer_repo.update_last_seen_at(session, customer_id)
    await session.commit()
