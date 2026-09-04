from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth.dependencies import require_dispatcher
from database.session import get_db
from models.delivery import DeliveryStatus
from models.rider import Rider
from models.user import User
from schemas.rider import RiderResponse, RiderUserSummary

router = APIRouter(
    prefix="/riders",
    tags=["riders"],
)


@router.get(
    "",
    response_model=List[RiderResponse],
    summary="List riders in the rider directory",
)
def list_riders(
    available_only: bool = Query(
        default=False,
        description="If true, only return riders currently marked AVAILABLE",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_dispatcher),
):
    """
    Returns the rider directory: identity, vehicle info, current location,
    and availability, so a dispatcher can choose who to assign a delivery to
    without needing to already know a rider's profile ID.

    Restricted to dispatchers, since phone numbers and live location are
    operational data rather than something every role should be able to browse.
    """
    query = db.query(Rider)
    if available_only:
        query = query.filter(Rider.availability_status == "AVAILABLE")

    riders = query.all()

    return [
        RiderResponse(
            id=rider.id,
            user=RiderUserSummary.model_validate(rider.user),
            availability_status=rider.availability_status,
            vehicle_type=rider.vehicle_type,
            plate_number=rider.plate_number,
            location=rider.location,
            active_delivery_count=sum(
                1
                for delivery in rider.assigned_deliveries
                if delivery.status in (DeliveryStatus.ASSIGNED, DeliveryStatus.PICKED_UP)
            ),
        )
        for rider in riders
    ]
