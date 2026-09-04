from typing import Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.delivery import Delivery, DeliveryStatus
from models.delivery_status_history import DeliveryStatusHistory
from models.rider import Rider
from models.user import User, UserRole
from schemas.delivery import DeliveryCreate


# Business rule state machine:
# Defines permitted delivery status transitions.
ALLOWED_TRANSITIONS: Dict[DeliveryStatus, Set[DeliveryStatus]] = {
    DeliveryStatus.OPEN: {
        DeliveryStatus.ASSIGNED,
    },
    DeliveryStatus.ASSIGNED: {
        DeliveryStatus.PICKED_UP,
        DeliveryStatus.FAILED,
    },
    DeliveryStatus.PICKED_UP: {
        DeliveryStatus.DELIVERED,
        DeliveryStatus.FAILED,
    },
    DeliveryStatus.FAILED: {
        DeliveryStatus.ASSIGNED,
    },
    DeliveryStatus.DELIVERED: set(),
}


def is_valid_transition(
    current_status: DeliveryStatus,
    new_status: DeliveryStatus,
) -> bool:
    """
    Check whether a delivery status transition is allowed.
    """
    allowed_targets = ALLOWED_TRANSITIONS.get(current_status, set())
    return new_status in allowed_targets


def create_delivery_record(
    db: Session,
    delivery_in: DeliveryCreate,
) -> Delivery:
    """
    Create a new delivery request.

    The creator must:
    - Exist in the users table.
    - Have the RETAILER role.

    New deliveries start in OPEN status and receive
    an initial status history record.
    """

    # 1. Validate creator existence
    creator = db.get(User, delivery_in.creator_id)

    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {delivery_in.creator_id} not found",
        )

    # 2. Validate creator role
    if creator.role != UserRole.RETAILER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"User with ID {delivery_in.creator_id} has role "
                f"'{getattr(creator.role, 'value', creator.role)}', "
                f"but only users with '{UserRole.RETAILER.value}' "
                "role can create delivery requests"
            ),
        )

    # 3. Create delivery
    new_delivery = Delivery(
        item_description=delivery_in.item_description,
        pickup_address=delivery_in.pickup_address,
        customer_name=delivery_in.customer_name,
        customer_phone=delivery_in.customer_phone,
        delivery_address=delivery_in.delivery_address,
        retailer_id=delivery_in.creator_id,
        status=DeliveryStatus.OPEN,
        assigned_by=None,
        assigned_rider_id=None,
    )

    db.add(new_delivery)
    db.flush()

    # 4. Create initial status history
    initial_history = DeliveryStatusHistory(
        delivery_id=new_delivery.id,
        status=DeliveryStatus.OPEN,
    )

    db.add(initial_history)

    # 5. Commit
    db.commit()
    db.refresh(new_delivery)

    return new_delivery


def list_delivery_records(
    db: Session,
    status: Optional[DeliveryStatus] = None,
    rider_id: Optional[int] = None,
    retailer_id: Optional[int] = None,
    dispatcher_id: Optional[int] = None,
) -> List[Delivery]:
    """
    Retrieve deliveries with optional filters.

    Supported filters:
    - status
    - rider_id
    - retailer_id
    - dispatcher_id

    Results are ordered newest first.
    """

    stmt = select(Delivery)

    if status is not None:
        stmt = stmt.where(Delivery.status == status)

    if rider_id is not None:
        stmt = stmt.where(
            Delivery.assigned_rider_id == rider_id
        )

    if retailer_id is not None:
        stmt = stmt.where(
            Delivery.retailer_id == retailer_id
        )

    if dispatcher_id is not None:
        stmt = stmt.where(
            Delivery.assigned_by == dispatcher_id
        )

    stmt = stmt.order_by(Delivery.created_at.desc())

    return list(db.scalars(stmt).all())


def validate_and_apply_status_transition(
    db: Session,
    delivery: Delivery,
    new_status: DeliveryStatus,
    changed_by: int,
) -> Delivery:
    """
    Validate and apply a delivery status transition.

    The actor must exist, and the requested transition
    must be permitted by ALLOWED_TRANSITIONS.
    """

    # 1. Validate actor
    actor = db.get(User, changed_by)

    if not actor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {changed_by} not found",
        )

    # 2. Validate status transition
    if not is_valid_transition(
        delivery.status,
        new_status,
    ):
        allowed_targets = [
            transition.value
            for transition in ALLOWED_TRANSITIONS.get(
                delivery.status,
                set(),
            )
        ]

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status transition from "
                f"'{getattr(delivery.status, 'value', delivery.status)}' "
                f"to '{new_status.value}'. "
                f"Allowed transitions from "
                f"'{getattr(delivery.status, 'value', delivery.status)}': "
                f"{allowed_targets}"
            ),
        )

    # 3. Update delivery status
    delivery.status = new_status

    # 4. Record status history
    history_entry = DeliveryStatusHistory(
        delivery_id=delivery.id,
        status=new_status,
    )

    db.add(history_entry)

    # 5. Commit
    db.commit()
    db.refresh(delivery)

    return delivery


def assign_delivery_to_rider(
    db: Session,
    delivery_id: int,
    rider_id: int,
    dispatcher_id: int,
) -> Delivery:
    """
    Assign an OPEN or FAILED delivery to an AVAILABLE rider
    by a dispatcher.

    Validates:
    - Delivery exists.
    - Delivery is OPEN or FAILED.
    - Dispatcher exists.
    - Dispatcher has DISPATCHER role.
    - Rider record exists.
    - Rider's linked user exists.
    - Rider has RIDER role.
    - Rider is AVAILABLE.

    Updates:
    - assigned_by
    - assigned_rider_id
    - status

    Also creates an ASSIGNED status history record.
    """

    # 1. Find delivery
    delivery = db.get(Delivery, delivery_id)

    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery with ID {delivery_id} not found",
        )

    # 2. Validate delivery status
    if delivery.status == DeliveryStatus.DELIVERED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "DELIVERED deliveries are terminal and "
                "cannot be assigned or reassigned"
            ),
        )

    if delivery.status not in (
        DeliveryStatus.OPEN,
        DeliveryStatus.FAILED,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Delivery with ID {delivery_id} is currently in "
                f"'{getattr(delivery.status, 'value', delivery.status)}' "
                "status and cannot be reassigned. "
                "Only 'OPEN' or 'FAILED' deliveries can be assigned "
                "to a rider."
            ),
        )

    # 3. Validate dispatcher
    dispatcher = db.get(User, dispatcher_id)

    if not dispatcher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispatcher with ID {dispatcher_id} not found",
        )

    if dispatcher.role != UserRole.DISPATCHER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"User with ID {dispatcher_id} has role "
                f"'{getattr(dispatcher.role, 'value', dispatcher.role)}', "
                f"but only users with '{UserRole.DISPATCHER.value}' "
                "role can assign deliveries"
            ),
        )

    # 4. Validate rider record
    rider = db.get(Rider, rider_id)

    if not rider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rider with ID {rider_id} not found",
        )

    # 5. Validate rider's linked user
    rider_user = db.get(User, rider.user_id)

    if not rider_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"User with ID {rider.user_id} "
                f"for rider {rider_id} not found"
            ),
        )

    # 6. Validate rider role
    if rider_user.role != UserRole.RIDER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"User with ID {rider.user_id} has role "
                f"'{getattr(rider_user.role, 'value', rider_user.role)}', "
                f"but only users with '{UserRole.RIDER.value}' "
                "role can be assigned as riders"
            ),
        )

    # 7. Validate rider availability
    if rider.availability_status != "AVAILABLE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Rider with ID {rider_id} "
                "is not available for assignment"
            ),
        )

    # 8. Apply assignment
    delivery.assigned_by = dispatcher_id
    delivery.assigned_rider_id = rider_id
    delivery.status = DeliveryStatus.ASSIGNED

    # 9. Record assignment in status history
    history_entry = DeliveryStatusHistory(
        delivery_id=delivery.id,
        status=DeliveryStatus.ASSIGNED,
    )

    db.add(history_entry)

    # 10. Commit
    db.commit()
    db.refresh(delivery)

    return delivery