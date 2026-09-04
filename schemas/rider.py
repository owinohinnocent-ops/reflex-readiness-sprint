from typing import Optional

from pydantic import BaseModel, ConfigDict


class RiderUserSummary(BaseModel):
    """Minimal identity info about the user behind a rider profile."""

    id: int
    name: str
    phone: str

    model_config = ConfigDict(from_attributes=True)


class RiderResponse(BaseModel):
    """
    Full rider directory entry: identity + vehicle + availability.
    Used by the dispatcher-facing rider directory endpoint.
    """

    id: int
    user: RiderUserSummary
    availability_status: Optional[str] = None
    vehicle_type: Optional[str] = None
    plate_number: Optional[str] = None
    location: Optional[str] = None
    active_delivery_count: int = 0

    model_config = ConfigDict(from_attributes=True)
