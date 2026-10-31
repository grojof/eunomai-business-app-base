"""The demo's tables: the equipment a fictional company maintains, and the work done on it."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

EQUIPMENT_STATUSES = ("in_service", "due_soon", "stopped")
WORK_ORDER_STATUSES = ("reported", "planned", "in_progress", "checked", "closed")


def _one_of(values: tuple[str, ...]) -> str:
    return "status IN (" + ", ".join(f"'{value}'" for value in values) + ")"


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (CheckConstraint(_one_of(EQUIPMENT_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    next_inspection: Mapped[date] = mapped_column(index=True)
    cost: Mapped[Decimal]
    updated_at: Mapped[datetime]

    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="equipment", passive_deletes=True)


class WorkOrder(Base):
    __tablename__ = "work_order"
    __table_args__ = (CheckConstraint(_one_of(WORK_ORDER_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), index=True)
    hours: Mapped[Decimal]
    cost: Mapped[Decimal]
    opened_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]

    equipment: Mapped[Equipment] = relationship(back_populates="work_orders")
