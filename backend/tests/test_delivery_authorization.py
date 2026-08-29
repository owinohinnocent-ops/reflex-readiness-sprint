import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth.dependencies import get_current_user, require_retailer
from auth.passwords import hash_password
from database.base import Base
from models.delivery import DeliveryStatus
from models.rider import Rider
from models.user import User, UserRole
from routes.deliveries import (
    assign_delivery,
    create_delivery,
    get_delivery,
    list_deliveries,
    update_delivery_status,
)
from schemas.delivery import (
    DeliveryAssignRequest,
    DeliveryCreate,
    DeliveryStatusUpdate,
)
from services.delivery_service import (
    assign_delivery_to_rider,
    create_delivery_record,
)


class TestDeliveryAuthorization(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)

        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.users = {}

        # Create users
        self.users["retailer"] = self._user(
            1,
            "Retailer",
            "0700000001",
            UserRole.RETAILER,
        )

        self.users["other_retailer"] = self._user(
            2,
            "Other Retailer",
            "0700000002",
            UserRole.RETAILER,
        )

        self.users["dispatcher"] = self._user(
            3,
            "Dispatcher",
            "0700000003",
            UserRole.DISPATCHER,
        )

        self.users["other_dispatcher"] = self._user(
            4,
            "Other Dispatcher",
            "0700000004",
            UserRole.DISPATCHER,
        )

        self.users["rider"] = self._user(
            5,
            "Rider",
            "0700000005",
            UserRole.RIDER,
        )

        self.users["other_rider"] = self._user(
            6,
            "Other Rider",
            "0700000006",
            UserRole.RIDER,
        )

        # Create riders as AVAILABLE
        self.db.add_all(
            [
                Rider(
                    id=101,
                    user=self.users["rider"],
                    availability_status="AVAILABLE",
                ),
                Rider(
                    id=102,
                    user=self.users["other_rider"],
                    availability_status="AVAILABLE",
                ),
            ]
        )

        self.db.commit()

        self.rider = self.db.get(Rider, 101)
        self.other_rider = self.db.get(Rider, 102)

    def _user(self, user_id, name, phone, role):
        user = User(
            id=user_id,
            name=name,
            phone=phone,
            password_hash=hash_password("password"),
            role=role,
        )

        self.db.add(user)
        self.db.flush()

        return user

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _delivery_payload(self, creator_id=1):
        return DeliveryCreate(
            item_description="Package",
            pickup_address="Pickup",
            customer_name="Customer",
            customer_phone="0712345678",
            delivery_address="Delivery",
            creator_id=creator_id,
        )

    def test_unauthenticated_delivery_request_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            get_current_user(None, self.db)

        self.assertEqual(
            context.exception.status_code,
            401,
        )

    def test_wrong_role_is_rejected_for_creation(self):
        with self.assertRaises(HTTPException) as context:
            require_retailer(
                current_user=self.users["dispatcher"]
            )

        self.assertEqual(
            context.exception.status_code,
            403,
        )

    def test_authenticated_retailer_creation_and_conflicting_creator(self):
        delivery = create_delivery(
            self._delivery_payload(1),
            self.db,
            self.users["retailer"],
        )

        self.assertEqual(
            delivery.retailer_id,
            self.users["retailer"].id,
        )

        with self.assertRaises(HTTPException) as context:
            create_delivery(
                self._delivery_payload(2),
                self.db,
                self.users["retailer"],
            )

        self.assertEqual(
            context.exception.status_code,
            403,
        )

    def test_authenticated_dispatcher_assignment_and_conflict(self):
        delivery = create_delivery_record(
            self.db,
            self._delivery_payload(),
        )

        request = DeliveryAssignRequest(
            rider_id=self.rider.id,
            dispatcher_id=self.users["dispatcher"].id,
        )

        assigned = assign_delivery(
            delivery.id,
            request,
            self.db,
            self.users["dispatcher"],
        )

        self.assertEqual(
            assigned.assigned_by,
            self.users["dispatcher"].id,
        )

        self.assertEqual(
            assigned.assigned_rider_id,
            self.rider.id,
        )

        second_delivery = create_delivery_record(
            self.db,
            self._delivery_payload(),
        )

        conflicting_request = DeliveryAssignRequest(
            rider_id=self.rider.id,
            dispatcher_id=self.users["other_dispatcher"].id,
        )

        with self.assertRaises(HTTPException) as context:
            assign_delivery(
                second_delivery.id,
                conflicting_request,
                self.db,
                self.users["dispatcher"],
            )

        self.assertEqual(
            context.exception.status_code,
            403,
        )

    def test_status_actor_comes_from_authenticated_user(self):
        delivery = create_delivery_record(
            self.db,
            self._delivery_payload(),
        )

        update = DeliveryStatusUpdate(
            status=DeliveryStatus.ASSIGNED,
            changed_by=self.users["retailer"].id,
        )

        updated = update_delivery_status(
            delivery.id,
            update,
            self.db,
            self.users["dispatcher"],
        )

        self.assertEqual(
            updated.status,
            DeliveryStatus.ASSIGNED,
        )

    def test_unauthorized_status_transition_is_rejected(self):
        delivery = create_delivery_record(
            self.db,
            self._delivery_payload(),
        )

        update = DeliveryStatusUpdate(
            status=DeliveryStatus.ASSIGNED,
        )

        with self.assertRaises(HTTPException) as context:
            update_delivery_status(
                delivery.id,
                update,
                self.db,
                self.users["retailer"],
            )

        self.assertEqual(
            context.exception.status_code,
            403,
        )

    def test_assigned_rider_can_transition_and_different_rider_cannot(self):
        delivery = create_delivery_record(
            self.db,
            self._delivery_payload(),
        )

        assign_delivery_to_rider(
            self.db,
            delivery.id,
            self.rider.id,
            self.users["dispatcher"].id,
        )

        pickup = DeliveryStatusUpdate(
            status=DeliveryStatus.PICKED_UP,
        )

        # Different rider must not update the delivery
        with self.assertRaises(HTTPException) as context:
            update_delivery_status(
                delivery.id,
                pickup,
                self.db,
                self.users["other_rider"],
            )

        self.assertEqual(
            context.exception.status_code,
            403,
        )

        # Assigned rider can update the delivery
        updated = update_delivery_status(
            delivery.id,
            pickup,
            self.db,
            self.users["rider"],
        )

        self.assertEqual(
            updated.status,
            DeliveryStatus.PICKED_UP,
        )

    def test_retailer_visibility_is_limited_to_own_deliveries(self):
        own = create_delivery_record(
            self.db,
            self._delivery_payload(1),
        )

        other = create_delivery_record(
            self.db,
            self._delivery_payload(2),
        )

        visible = list_deliveries(
            status=None,
            rider_id=None,
            retailer_id=None,
            dispatcher_id=None,
            db=self.db,
            current_user=self.users["retailer"],
        )

        self.assertEqual(
            {delivery.id for delivery in visible},
            {own.id},
        )

        self.assertEqual(
            get_delivery(
                own.id,
                self.db,
                self.users["retailer"],
            ).id,
            own.id,
        )

        with self.assertRaises(HTTPException) as context:
            get_delivery(
                other.id,
                self.db,
                self.users["retailer"],
            )

        self.assertEqual(
            context.exception.status_code,
            403,
        )

    def test_rider_visibility_is_limited_to_assigned_rider_id(self):
        assigned = create_delivery_record(
            self.db,
            self._delivery_payload(),
        )

        unassigned = create_delivery_record(
            self.db,
            self._delivery_payload(),
        )

        assign_delivery_to_rider(
            self.db,
            assigned.id,
            self.rider.id,
            self.users["dispatcher"].id,
        )

        visible = list_deliveries(
            status=None,
            rider_id=None,
            retailer_id=None,
            dispatcher_id=None,
            db=self.db,
            current_user=self.users["rider"],
        )

        self.assertEqual(
            [delivery.id for delivery in visible],
            [assigned.id],
        )

        with self.assertRaises(HTTPException) as context:
            get_delivery(
                unassigned.id,
                self.db,
                self.users["rider"],
            )

        self.assertEqual(
            context.exception.status_code,
            403,
        )

    def test_dispatcher_can_view_all_deliveries(self):
        first = create_delivery_record(
            self.db,
            self._delivery_payload(1),
        )

        second = create_delivery_record(
            self.db,
            self._delivery_payload(2),
        )

        visible = list_deliveries(
            status=None,
            rider_id=None,
            retailer_id=None,
            dispatcher_id=None,
            db=self.db,
            current_user=self.users["dispatcher"],
        )

        self.assertEqual(
            {delivery.id for delivery in visible},
            {first.id, second.id},
        )


if __name__ == "__main__":
    unittest.main()