import enum
from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.base import Base

if TYPE_CHECKING:
    from .delivery import Delivery
    from .delivery_status_history import DeliveryStatusHistory
    from .rider import Rider


class UserRole(str, enum.Enum):
    RETAILER = "retailer"
    DISPATCHER = "dispatcher"
    RIDER = "rider"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    created_deliveries: Mapped[List["Delivery"]] = relationship(
        "Delivery",
        back_populates="creator",
        foreign_keys="[Delivery.retailer_id]",
    )
    dispatched_deliveries: Mapped[List["Delivery"]] = relationship(
        "Delivery",
        back_populates="dispatcher",
        foreign_keys="[Delivery.assigned_by]",
    )
    rider_profile: Mapped["Rider"] = relationship(
        "Rider",
        back_populates="user",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name='{self.name}', role='{self.role}')>"
