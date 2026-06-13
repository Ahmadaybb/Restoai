"""CustomerRepository — Postgres-backed customer and address access."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Address as AddressORM
from app.db.models import Customer as CustomerORM
from app.domain.customer import Address, Customer


def _orm_address(row: AddressORM) -> Address:
    return Address(
        id=row.id,
        customer_id=row.customer_id,
        kind=row.kind,  # type: ignore[arg-type]
        text_value=row.text_value,
        lat=row.lat,
        lon=row.lon,
        area_label=row.area_label,
        in_zone=row.in_zone,
        created_at=row.created_at,
    )


def _orm_to_domain(row: CustomerORM) -> Customer:
    return Customer(
        id=row.id,
        phone_e164=row.phone_e164,
        telegram_user_id=row.telegram_user_id,
        display_name=row.display_name,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        addresses=[_orm_address(a) for a in (row.addresses or [])],
    )


async def find_by_id(
    session: AsyncSession, customer_id: uuid.UUID
) -> Customer | None:
    result = await session.execute(
        select(CustomerORM)
        .where(CustomerORM.id == customer_id)
        .options(selectinload(CustomerORM.addresses))
    )
    row = result.scalar_one_or_none()
    return _orm_to_domain(row) if row else None


async def find_by_phone_e164(
    session: AsyncSession, phone: str
) -> Customer | None:
    result = await session.execute(
        select(CustomerORM)
        .where(CustomerORM.phone_e164 == phone)
        .options(selectinload(CustomerORM.addresses))
    )
    row = result.scalar_one_or_none()
    return _orm_to_domain(row) if row else None


async def find_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> Customer | None:
    result = await session.execute(
        select(CustomerORM)
        .where(CustomerORM.telegram_user_id == telegram_id)
        .options(selectinload(CustomerORM.addresses))
    )
    row = result.scalar_one_or_none()
    return _orm_to_domain(row) if row else None


async def create(session: AsyncSession, customer: Customer) -> Customer:
    row = CustomerORM(
        id=customer.id,
        phone_e164=customer.phone_e164,
        telegram_user_id=customer.telegram_user_id,
        display_name=customer.display_name,
    )
    session.add(row)
    await session.flush()
    return customer


async def update_fields(
    session: AsyncSession,
    customer_id: uuid.UUID,
    **kwargs: object,
) -> None:
    await session.execute(
        update(CustomerORM).where(CustomerORM.id == customer_id).values(**kwargs)
    )


async def update_last_seen_at(
    session: AsyncSession, customer_id: uuid.UUID
) -> None:
    await update_fields(
        session, customer_id, last_seen_at=datetime.now(tz=UTC)
    )


async def save_address(session: AsyncSession, address: Address) -> Address:
    row = AddressORM(
        id=address.id,
        customer_id=address.customer_id,
        kind=address.kind,
        text_value=address.text_value,
        lat=address.lat,
        lon=address.lon,
        area_label=address.area_label,
        in_zone=address.in_zone,
    )
    session.add(row)
    await session.flush()
    return address
