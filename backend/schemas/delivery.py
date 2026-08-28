from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from models.delivery import DeliveryStatus


class DeliveryCreate(BaseModel):
    """
    Schema for creating a new delivery request.
    Validates required fields are non-empty strings.
    """
    item_description: str = Field(
        ...,
        description="Description of the item to be delivered",
        examples=["5kg Maize Flour and Cooking Oil"],
    )
    pickup_address: str = Field(
        ...,
        description="Pickup address of the retailer shop",
        examples=["Biashara Street, Stall 12, Nairobi"],
    )
    customer_name: str = Field(
        ...,
        description="Full name of the recipient customer",
        examples=["Jane Wanjiku"],
    )
    customer_phone: str = Field(
        ...,
        description="Phone number of the recipient customer",
        examples=["+254712345678"],
    )
    delivery_address: str = Field(
        ...,
        description="Destination delivery address",
        examples=["Kileleshwa, App 4B, Nairobi"],
    )
    # Temporary field until authentication is implemented
    creator_id: int = Field(
        ...,
        gt=0,
        description="Temporary creator user ID (must belong to an existing RETAILER user)",
        examples=[1],
    )

    @field_validator(
        "item_description",
        "pickup_address",
        "customer_name",
        "customer_phone",
        "delivery_address",
    )
    @classmethod
    def validate_non_empty_string(cls, value: str, info) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"'{info.field_name}' must not be empty or blank")
        return value.strip()


class DeliveryStatusUpdate(BaseModel):
    """
    Schema for updating a delivery's status.
    """
    status: DeliveryStatus = Field(
        ...,
        description="The new target delivery status",
        examples=["ASSIGNED"],
    )
    changed_by: Optional[int] = Field(
        default=None,
        gt=0,
        description="Temporary user ID performing the change (defaults to creator ID in dev mode)",
        examples=[1],
    )

class DeliveryAssignRequest(BaseModel):
    """
    Schema for assigning a dispatcher and rider to a delivery (used by Person 2's assignment API).
    """
    rider_id: int = Field(
        ...,
        gt=0,
        description="ID of the rider being assigned (must have role RIDER)",
        examples=[3],
    )
    dispatcher_id: int = Field(
        ...,
        gt=0,
        description="ID of the dispatcher assigning the order (must have role DISPATCHER)",
        examples=[2],
    )


class DeliveryStatusHistoryResponse(BaseModel):
    """
    Schema for delivery status history audit records.
    """
    id: int
    delivery_id: int
    status: DeliveryStatus
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeliveryResponse(BaseModel):
    """
    Schema for returning delivery details in API responses.
    """
    id: int
    item_description: str
    pickup_address: str
    customer_name: str
    customer_phone: str
    delivery_address: str
    retailer_id: int
    assigned_by: Optional[int] = None
    assigned_rider_id: Optional[int] = None
    status: DeliveryStatus
    created_at: datetime
    updated_at: datetime
    status_history: List[DeliveryStatusHistoryResponse] = []

    model_config = ConfigDict(from_attributes=True)
