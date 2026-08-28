from typing import Dict, List, Optional, Set
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from models.delivery import Delivery, DeliveryStatus
from models.delivery_status_history import DeliveryStatusHistory
from models.rider import Rider
from models.user import User, UserRole
from schemas.delivery import DeliveryCreate

# Business rule state machine: defines permitted status transitions
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
    DeliveryStatus.DELIVERED: set(),  # Terminal state: no outgoing transitions allowed
}


def is_valid_transition(current_status: DeliveryStatus, new_status: DeliveryStatus) -> bool:
    """
    Checks if a transition from current_status to new_status is permitted.
    """
    allowed_targets = ALLOWED_TRANSITIONS.get(current_status, set())
    return new_status in allowed_targets


def create_delivery_record(
    db: Session,
    delivery_in: DeliveryCreate,
) -> Delivery:
    """
    Validates creator existence, verifies RETAILER role, creates the delivery in OPEN status,
    and inserts the initial status history record atomically.
    """
    # 1. Validate creator existence
    creator = db.get(User, delivery_in.creator_id)
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {delivery_in.creator_id} not found",
        )

    # 2. Validate that creator is a RETAILER
    if creator.role != UserRole.RETAILER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"User with ID {delivery_in.creator_id} has role '{getattr(creator.role, 'value', creator.role)}', "
                f"but only users with '{UserRole.RETAILER.value}' role can create delivery requests"
            ),
        )

    # 3. Create the new Delivery instance
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

    # 4. Create initial status history entry
    initial_history = DeliveryStatusHistory(
        delivery_id=new_delivery.id,
        status=DeliveryStatus.OPEN,
    )
    db.add(initial_history)

    # 5. Commit transaction atomically
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
    Retrieves deliveries with optional filtering by status, rider_id, retailer_id, or dispatcher_id.
    Results are consistently ordered newest first (created_at DESC).
    """
    stmt = select(Delivery)

    if status is not None:
        stmt = stmt.where(Delivery.status == status)
    if rider_id is not None:
        stmt = stmt.where(Delivery.assigned_rider_id == rider_id)
    if retailer_id is not None:
        stmt = stmt.where(Delivery.retailer_id == retailer_id)
    if dispatcher_id is not None:
        stmt = stmt.where(Delivery.assigned_by == dispatcher_id)

    stmt = stmt.order_by(Delivery.created_at.desc())
    return list(db.scalars(stmt).all())


def validate_and_apply_status_transition(
    db: Session,
    delivery: Delivery,
    new_status: DeliveryStatus,
    changed_by: int,
) -> Delivery:
    """
    Validates business rules for the delivery status transition:
    - Verifies that changed_by refers to an existing user.
    - Validates that the transition from delivery.status to new_status is allowed.
    If valid, updates delivery.status and adds a history entry atomically.
    If invalid, raises an appropriate HTTPException without modifying the database.
    """
    # 1. Validate that changed_by user exists
    actor = db.get(User, changed_by)
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {changed_by} not found",
        )

    # 2. Validate state machine transition
    if not is_valid_transition(delivery.status, new_status):
        allowed_targets = [s.value for s in ALLOWED_TRANSITIONS.get(delivery.status, set())]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status transition from '{getattr(delivery.status, 'value', delivery.status)}' to '{new_status.value}'. "
                f"Allowed transitions from '{getattr(delivery.status, 'value', delivery.status)}': {allowed_targets}"
            ),
        )

    # 3. Update delivery status
    delivery.status = new_status

    # 4. Record status history entry
    history_entry = DeliveryStatusHistory(
        delivery_id=delivery.id,
        status=new_status,
    )
    db.add(history_entry)

    # 5. Commit delivery status update and history record atomically
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
    Service helper for Person 2's Dispatcher/Rider Assignment logic.
    
    Assigns an OPEN or FAILED delivery to a rider by a dispatcher.
    
    Validates:
    - Delivery exists.
    - Delivery is in OPEN or FAILED status (DELIVERED is terminal, ASSIGNED/PICKED_UP cannot be silently reassigned).
    - Dispatcher exists and has DISPATCHER role.
    - Rider exists and has RIDER role.

    Updates:
    - delivery.assigned_by = dispatcher_id
    - delivery.assigned_rider_id = rider_id
    - delivery.status = DeliveryStatus.ASSIGNED
    - Creates a DeliveryStatusHistory record with status ASSIGNED and changed_by = dispatcher_id.
    - Commits and returns the updated delivery.
    """
    # 1. Lookup delivery
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery with ID {delivery_id} not found",
        )

    # 2. Validate assignability based on state machine rules
    if delivery.status == DeliveryStatus.DELIVERED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DELIVERED deliveries are terminal and cannot be assigned or reassigned",
        )

    if delivery.status not in (DeliveryStatus.OPEN, DeliveryStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Delivery with ID {delivery_id} is currently in '{getattr(delivery.status, 'value', delivery.status)}' status and cannot be reassigned. "
                "Only 'OPEN' or 'FAILED' deliveries can be assigned to a rider."
            ),
        )

    # 3. Validate Dispatcher
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
                f"User with ID {dispatcher_id} has role '{getattr(dispatcher.role, 'value', dispatcher.role)}', "
                f"but only users with '{UserRole.DISPATCHER.value}' role can assign deliveries"
            ),
        )

    # 4. Validate Rider record and its linked user
    rider = db.get(Rider, rider_id)
    if not rider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rider with ID {rider_id} not found",
        )
    rider_user = db.get(User, rider.user_id)
    if not rider_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {rider.user_id} for rider {rider_id} not found",
        )
    if rider_user.role != UserRole.RIDER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"User with ID {rider.user_id} has role '{getattr(rider_user.role, 'value', rider_user.role)}', "
                f"but only users with '{UserRole.RIDER.value}' role can be assigned as riders"
            ),
        )

    # 5. Apply Assignment and Transition to ASSIGNED
    delivery.assigned_by = dispatcher_id
    delivery.assigned_rider_id = rider_id
    delivery.status = DeliveryStatus.ASSIGNED

    # 6. Record Status History Entry
    history_entry = DeliveryStatusHistory(
        delivery_id=delivery.id,
        status=DeliveryStatus.ASSIGNED,
    )
    db.add(history_entry)

    # 7. Commit atomically
    db.commit()
    db.refresh(delivery)

    return delivery
