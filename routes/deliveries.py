from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from auth.dependencies import get_current_user, require_dispatcher, require_retailer
from database.session import get_db
from models.delivery import Delivery, DeliveryStatus
from models.rider import Rider
from models.user import User, UserRole
from schemas.delivery import (
    DeliveryAssignRequest,
    DeliveryCreate,
    DeliveryResponse,
    DeliveryStatusUpdate,
)
from services.delivery_service import (
    assign_delivery_to_rider,
    create_delivery_record,
    list_delivery_records,
    validate_and_apply_status_transition,
)

router = APIRouter(
    prefix="/deliveries",
    tags=["deliveries"],
)


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def _authorize_delivery_visibility(db: Session, delivery: Delivery, current_user: User) -> None:
    role = getattr(current_user.role, "value", current_user.role)
    if role == UserRole.DISPATCHER.value:
        return
    if role == UserRole.RETAILER.value and delivery.retailer_id == current_user.id:
        return
    if role == UserRole.RIDER.value:
        rider = db.query(Rider).filter(Rider.user_id == current_user.id).first()
        if rider is not None and delivery.assigned_rider_id == rider.id:
            return
    raise _forbidden()


def _authorize_status_transition(
    db: Session,
    delivery: Delivery,
    new_status: DeliveryStatus,
    current_user: User,
) -> None:
    role = getattr(current_user.role, "value", current_user.role)
    current_status = getattr(delivery.status, "value", delivery.status)
    target_status = getattr(new_status, "value", new_status)
    if target_status == DeliveryStatus.ASSIGNED.value and current_status in {
        DeliveryStatus.OPEN.value,
        DeliveryStatus.FAILED.value,
    }:
        if role == UserRole.DISPATCHER.value:
            return
    elif current_status in {
        DeliveryStatus.ASSIGNED.value,
        DeliveryStatus.PICKED_UP.value,
    } and target_status in {
        DeliveryStatus.PICKED_UP.value,
        DeliveryStatus.DELIVERED.value,
        DeliveryStatus.FAILED.value,
    }:
        rider = db.query(Rider).filter(Rider.user_id == current_user.id).first()
        if role == UserRole.RIDER.value and rider is not None and delivery.assigned_rider_id == rider.id:
            return
    raise _forbidden()


@router.post(
    "",
    response_model=DeliveryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new delivery request",
)
def create_delivery(
    delivery_in: DeliveryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_retailer),
):
    """
    Creates a new delivery request:
    - Validates that creator_id exists and belongs to a RETAILER user.
    - Sets initial status to OPEN.
    - Leaves assigned_by and assigned_rider_id as null.
    - Records an initial DeliveryStatusHistory entry.
    """
    if delivery_in.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Creator identity does not match authenticated user")
    return create_delivery_record(db=db, delivery_in=delivery_in)


@router.get(
    "",
    response_model=List[DeliveryResponse],
    summary="List all deliveries",
)
def list_deliveries(
    status: Optional[DeliveryStatus] = Query(
        default=None,
        description="Filter deliveries by status (OPEN, ASSIGNED, PICKED_UP, DELIVERED, FAILED)",
        examples=["OPEN"],
    ),
    rider_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Filter deliveries by assigned rider user ID",
        examples=[3],
    ),
    retailer_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Filter deliveries by creator (retailer) user ID",
        examples=[1],
    ),
    dispatcher_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Filter deliveries by assigned dispatcher user ID",
        examples=[2],
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves a list of deliveries, ordered with the newest first.
    Supports optional filtering by status, rider_id, retailer_id, and dispatcher_id.
    """
    role = getattr(current_user.role, "value", current_user.role)
    if role == UserRole.RETAILER.value:
        if retailer_id is not None and retailer_id != current_user.id:
            return []
        retailer_id = current_user.id
    elif role == UserRole.RIDER.value:
        rider = db.query(Rider).filter(Rider.user_id == current_user.id).first()
        if rider is None or (rider_id is not None and rider_id != rider.id):
            return []
        rider_id = rider.id

    return list_delivery_records(
        db=db,
        status=status,
        rider_id=rider_id,
        retailer_id=retailer_id,
        dispatcher_id=dispatcher_id,
    )


@router.get(
    "/{delivery_id}",
    response_model=DeliveryResponse,
    summary="Get delivery by ID",
)
def get_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves a single delivery by its ID.
    Returns HTTP 404 if the delivery does not exist.
    """
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery with ID {delivery_id} not found",
        )
    _authorize_delivery_visibility(db, delivery, current_user)
    return delivery


@router.patch(
    "/{delivery_id}/status",
    response_model=DeliveryResponse,
    summary="Update delivery status",
)
def update_delivery_status(
    delivery_id: int,
    status_update: DeliveryStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Updates the status of a delivery based on defined business rules:
    - Validates that changed_by user exists.
    - Validates state transitions (OPEN -> ASSIGNED -> PICKED_UP -> DELIVERED, etc.).
    - Rejects invalid transitions with HTTP 400 Bad Request.
    - DELIVERED is terminal.
    """
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery with ID {delivery_id} not found",
        )

    _authorize_status_transition(db, delivery, status_update.status, current_user)
    changed_by = current_user.id

    updated_delivery = validate_and_apply_status_transition(
        db=db,
        delivery=delivery,
        new_status=status_update.status,
        changed_by=changed_by,
    )
    return updated_delivery


@router.post(
    "/{delivery_id}/assign",
    response_model=DeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign delivery to rider",
)
def assign_delivery(
    delivery_id: int,
    assignment_in: DeliveryAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_dispatcher),
):
    """
    Assigns a delivery to a rider by a dispatcher.
    Delegates assignability, existence, and role validations to the delivery service.
    """
    if assignment_in.dispatcher_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dispatcher identity does not match authenticated user")
    return assign_delivery_to_rider(
        db=db,
        delivery_id=delivery_id,
        rider_id=assignment_in.rider_id,
        dispatcher_id=current_user.id,
    )
