"""The demo's tables: the equipment a fictional company maintains, and the work done on it."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ColumnElement, ForeignKey, String, Text, and_, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

EQUIPMENT_STATUSES = ("in_service", "due_soon", "stopped")
WORK_ORDER_STATUSES = ("reported", "planned", "in_progress", "checked", "closed")
OPEN_STATES = ("reported", "planned", "in_progress", "checked")
PRIORITIES = ("low", "normal", "high")
LOCATIONS = ("Workshop", "Packing", "Plant room", "Roof", "Warehouse")
LAST_DAY = date(2026, 10, 31)
"""The demo's today: its data ends here, and what is overdue is overdue on this day, whenever it is read."""
FIRST_MOMENT = datetime(2026, 1, 1, 12, tzinfo=UTC)
LAST_MOMENT = datetime(2026, 10, 31, 12, tzinfo=UTC)
"""At noon, so that no time zone moves the first or the last moment to another day, or another month."""


def _one_of(values: tuple[str, ...], column: str = "status") -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (CheckConstraint(_one_of(EQUIPMENT_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    location: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    next_inspection: Mapped[date] = mapped_column(index=True)
    cost: Mapped[Decimal] = mapped_column(index=True)
    updated_at: Mapped[datetime]

    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="equipment", passive_deletes=True)


class WorkOrder(Base):
    __tablename__ = "work_order"
    __table_args__ = (
        CheckConstraint(_one_of(WORK_ORDER_STATUSES), name="status"),
        CheckConstraint(_one_of(PRIORITIES, "priority"), name="priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), index=True)
    hours: Mapped[Decimal]
    cost: Mapped[Decimal]
    opened_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]
    planned_on: Mapped[date | None] = mapped_column(index=True)
    description: Mapped[str] = mapped_column(Text, server_default="")
    fault: Mapped[str | None] = mapped_column(String(24))
    priority: Mapped[str] = mapped_column(String(8), server_default="normal")
    crew: Mapped[int] = mapped_column(server_default="1")
    stop_needed: Mapped[bool] = mapped_column(server_default=false())

    equipment: Mapped[Equipment] = relationship(back_populates="work_orders")
    files: Mapped[list["WorkOrderFile"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan", passive_deletes=True, order_by="WorkOrderFile.id"
    )


class WorkOrderFile(Base):
    """A file attached to a work order. `name` is what a person called it, for showing; `stored_name` is ours."""

    __tablename__ = "work_order_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_order.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    stored_name: Mapped[str] = mapped_column(String(32), unique=True)
    media_type: Mapped[str] = mapped_column(String(40))
    size: Mapped[int]
    added_at: Mapped[datetime]

    work_order: Mapped[WorkOrder] = relationship(back_populates="files")


def overdue() -> ColumnElement[bool]:
    """Open work planned before the demo's today, the same question wherever it is asked."""
    return and_(WorkOrder.status.in_(OPEN_STATES), WorkOrder.planned_on < LAST_DAY)
