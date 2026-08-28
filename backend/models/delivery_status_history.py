from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.base import Base
from .delivery import DeliveryStatus

if TYPE_CHECKING:
    from .delivery import Delivery


class DeliveryStatusHistory(Base):
    __tablename__ = "delivery_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"), nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(String(30), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    delivery: Mapped["Delivery"] = relationship(
        "Delivery",
        back_populates="status_history",
        foreign_keys=[delivery_id],
    )
    def __repr__(self) -> str:
        return f"<DeliveryStatusHistory(id={self.id}, delivery_id={self.delivery_id}, status='{self.status}')>"
