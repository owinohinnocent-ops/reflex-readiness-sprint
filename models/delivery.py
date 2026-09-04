import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.base import Base

if TYPE_CHECKING:
    from .delivery_status_history import DeliveryStatusHistory
    from .rider import Rider
    from .user import User


class DeliveryStatus(str, enum.Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    pickup_address: Mapped[str] = mapped_column(Text, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)

    # Foreign Keys
    retailer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_rider_id: Mapped[Optional[int]] = mapped_column(ForeignKey("riders.id"), nullable=True)

    status: Mapped[DeliveryStatus] = mapped_column(
        String(30), default=DeliveryStatus.OPEN, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    creator: Mapped["User"] = relationship(
        "User",
        back_populates="created_deliveries",
        foreign_keys=[retailer_id],
    )
    dispatcher: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="dispatched_deliveries",
        foreign_keys=[assigned_by],
    )
    rider: Mapped[Optional["Rider"]] = relationship(
        "Rider",
        back_populates="assigned_deliveries",
        foreign_keys=[assigned_rider_id],
    )
    status_history: Mapped[List["DeliveryStatusHistory"]] = relationship(
        "DeliveryStatusHistory",
        back_populates="delivery",
        cascade="all, delete-orphan",
        order_by="DeliveryStatusHistory.changed_at.asc()",
    )

    def __repr__(self) -> str:
        return f"<Delivery(id={self.id}, status='{self.status}', customer='{self.customer_name}')>"
