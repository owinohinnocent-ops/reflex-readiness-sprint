import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.base import Base
from models.delivery import DeliveryStatus
from models.rider import Rider
from models.user import User, UserRole
from schemas.delivery import DeliveryAssignRequest, DeliveryCreate
from routes.deliveries import assign_delivery, list_deliveries
from services.delivery_service import (
    ALLOWED_TRANSITIONS,
    assign_delivery_to_rider,
    create_delivery_record,
    is_valid_transition,
    list_delivery_records,
    validate_and_apply_status_transition,
)


class TestDeliveryLogic(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.next_user_id = 1

        self.retailer = self._user(
            "Retailer Alice",
            "0711000001",
            UserRole.RETAILER,
        )
        self.retailer2 = self._user(
            "Retailer Daniel",
            "0711000099",
            UserRole.RETAILER,
        )
        self.dispatcher = self._user(
            "Dispatcher Bob",
            "0711000002",
            UserRole.DISPATCHER,
        )
        self.dispatcher2 = self._user(
            "Dispatcher Grace",
            "0711000098",
            UserRole.DISPATCHER,
        )

        rider_user = self._user(
            "Rider Charlie",
            "0711000003",
            UserRole.RIDER,
        )
        rider_user2 = self._user(
            "Rider Eric",
            "0711000097",
            UserRole.RIDER,
        )

        self.db.add_all(
            [
                Rider(
                    user=rider_user,
                    availability_status="AVAILABLE",
                ),
                Rider(
                    user=rider_user2,
                    availability_status="AVAILABLE",
                ),
            ]
        )

        self.db.commit()

        self.rider, self.rider2 = (
            self.db.query(Rider)
            .order_by(Rider.id)
            .all()
        )

    def _user(self, name, phone, role):
        user = User(
            id=self.next_user_id,
            name=name,
            phone=phone,
            password_hash="test-hash",
            role=role,
        )

        self.next_user_id += 1
        self.db.add(user)
        self.db.flush()

        return user

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _payload(self, retailer_id=None, description="Package"):
        return DeliveryCreate(
            item_description=description,
            pickup_address="Shop 1",
            customer_name="Customer",
            customer_phone="0700112233",
            delivery_address="Address 1",
            creator_id=retailer_id or self.retailer.id,
        )

    def _create_sample_delivery(
        self,
        retailer_id=None,
        description="Package",
    ):
        return create_delivery_record(
            self.db,
            self._payload(retailer_id, description),
        )

    def test_schema_trims_authoritative_address_fields(self):
        payload = DeliveryCreate(
            item_description="  Sugar 2kg  ",
            pickup_address="  Shop A  ",
            customer_name="  Jane Doe  ",
            customer_phone="  0712345678  ",
            delivery_address="  Apt 4B  ",
            creator_id=self.retailer.id,
        )

        self.assertEqual(payload.pickup_address, "Shop A")
        self.assertEqual(payload.delivery_address, "Apt 4B")

        with self.assertRaises(ValidationError):
            DeliveryCreate(
                item_description=" ",
                pickup_address="Shop",
                customer_name="Jane",
                customer_phone="0700",
                delivery_address="Address",
                creator_id=self.retailer.id,
            )

    def test_schema_rejects_empty_and_blank_strings(self):
        fields = {
            "item_description": "Description",
            "pickup_address": "Pickup",
            "customer_name": "Customer",
            "customer_phone": "0700",
            "delivery_address": "Delivery",
            "creator_id": self.retailer.id,
        }

        for field_name in (
            "item_description",
            "pickup_address",
            "customer_name",
            "customer_phone",
            "delivery_address",
        ):
            invalid_fields = fields.copy()
            invalid_fields[field_name] = "   "

            with self.subTest(field_name=field_name):
                with self.assertRaises(ValidationError):
                    DeliveryCreate(**invalid_fields)

    def test_create_delivery_maps_retailer_and_initial_history(self):
        delivery = self._create_sample_delivery()

        self.assertEqual(
            delivery.retailer_id,
            self.retailer.id,
        )
        self.assertIsNone(delivery.assigned_by)
        self.assertIsNone(delivery.assigned_rider_id)
        self.assertEqual(
            delivery.status,
            DeliveryStatus.OPEN,
        )
        self.assertEqual(
            len(delivery.status_history),
            1,
        )
        self.assertEqual(
            delivery.status_history[0].status,
            DeliveryStatus.OPEN,
        )
        self.assertIsNotNone(
            delivery.status_history[0].changed_at
        )

    def test_create_delivery_validates_retailer(self):
        with self.assertRaises(HTTPException) as context:
            create_delivery_record(
                self.db,
                self._payload(9999),
            )

        self.assertEqual(
            context.exception.status_code,
            404,
        )

        with self.assertRaises(HTTPException) as context:
            create_delivery_record(
                self.db,
                self._payload(self.dispatcher.id),
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

    def test_state_machine_is_preserved_without_history_actor_or_reason(
        self,
    ):
        self.assertEqual(
            ALLOWED_TRANSITIONS[DeliveryStatus.OPEN],
            {DeliveryStatus.ASSIGNED},
        )

        self.assertTrue(
            is_valid_transition(
                DeliveryStatus.PICKED_UP,
                DeliveryStatus.DELIVERED,
            )
        )

        self.assertFalse(
            is_valid_transition(
                DeliveryStatus.DELIVERED,
                DeliveryStatus.ASSIGNED,
            )
        )

        delivery = self._create_sample_delivery()

        transitions = [
            (
                DeliveryStatus.ASSIGNED,
                self.dispatcher.id,
            ),
            (
                DeliveryStatus.PICKED_UP,
                self.rider.user_id,
            ),
            (
                DeliveryStatus.FAILED,
                self.rider.user_id,
            ),
            (
                DeliveryStatus.ASSIGNED,
                self.dispatcher.id,
            ),
            (
                DeliveryStatus.PICKED_UP,
                self.rider.user_id,
            ),
            (
                DeliveryStatus.DELIVERED,
                self.rider.user_id,
            ),
        ]

        for new_status, actor in transitions:
            delivery = validate_and_apply_status_transition(
                self.db,
                delivery,
                new_status,
                actor,
            )

        self.assertEqual(
            delivery.status,
            DeliveryStatus.DELIVERED,
        )

        self.assertEqual(
            len(delivery.status_history),
            7,
        )

        self.assertFalse(
            hasattr(
                delivery.status_history[-1],
                "failure_reason",
            )
        )

    def test_invalid_transitions_are_rejected_without_mutation_or_history(
        self,
    ):
        delivery = self._create_sample_delivery()

        original_history_count = len(
            delivery.status_history
        )

        with self.assertRaises(HTTPException) as context:
            validate_and_apply_status_transition(
                self.db,
                delivery,
                DeliveryStatus.DELIVERED,
                self.retailer.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

        self.assertEqual(
            delivery.status,
            DeliveryStatus.OPEN,
        )

        self.assertEqual(
            len(delivery.status_history),
            original_history_count,
        )

    def test_status_transition_rejects_non_existent_actor(
        self,
    ):
        delivery = self._create_sample_delivery()

        with self.assertRaises(HTTPException) as context:
            validate_and_apply_status_transition(
                self.db,
                delivery,
                DeliveryStatus.ASSIGNED,
                99999,
            )

        self.assertEqual(
            context.exception.status_code,
            404,
        )

        self.assertEqual(
            delivery.status,
            DeliveryStatus.OPEN,
        )

    def test_assignment_uses_rider_id_and_assigned_by(self):
        delivery = self._create_sample_delivery()

        updated = assign_delivery_to_rider(
            self.db,
            delivery.id,
            self.rider.id,
            self.dispatcher.id,
        )

        self.assertEqual(
            updated.assigned_rider_id,
            self.rider.id,
        )

        self.assertEqual(
            updated.assigned_by,
            self.dispatcher.id,
        )

        self.assertEqual(
            updated.status,
            DeliveryStatus.ASSIGNED,
        )

        self.assertEqual(
            len(updated.status_history),
            2,
        )

    def test_assignment_succeeds_from_failed(self):
        delivery = self._create_sample_delivery()

        assign_delivery_to_rider(
            self.db,
            delivery.id,
            self.rider.id,
            self.dispatcher.id,
        )

        validate_and_apply_status_transition(
            self.db,
            delivery,
            DeliveryStatus.PICKED_UP,
            self.rider.user_id,
        )

        validate_and_apply_status_transition(
            self.db,
            delivery,
            DeliveryStatus.FAILED,
            self.rider.user_id,
        )

        updated = assign_delivery_to_rider(
            self.db,
            delivery.id,
            self.rider2.id,
            self.dispatcher2.id,
        )

        self.assertEqual(
            updated.status,
            DeliveryStatus.ASSIGNED,
        )

        self.assertEqual(
            updated.assigned_rider_id,
            self.rider2.id,
        )

        self.assertEqual(
            updated.assigned_by,
            self.dispatcher2.id,
        )

    def test_assignment_rejects_already_assigned(self):
        delivery = self._create_sample_delivery()

        assign_delivery_to_rider(
            self.db,
            delivery.id,
            self.rider.id,
            self.dispatcher.id,
        )

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider2.id,
                self.dispatcher.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

    def test_assignment_rejects_picked_up_and_delivered(
        self,
    ):
        delivery = self._create_sample_delivery()

        assign_delivery_to_rider(
            self.db,
            delivery.id,
            self.rider.id,
            self.dispatcher.id,
        )

        validate_and_apply_status_transition(
            self.db,
            delivery,
            DeliveryStatus.PICKED_UP,
            self.rider.user_id,
        )

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider2.id,
                self.dispatcher.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

        validate_and_apply_status_transition(
            self.db,
            delivery,
            DeliveryStatus.DELIVERED,
            self.rider.user_id,
        )

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider2.id,
                self.dispatcher.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

    def test_assignment_rejects_invalid_dispatcher_and_rider_entities(
        self,
    ):
        delivery = self._create_sample_delivery()

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider.id,
                99999,
            )

        self.assertEqual(
            context.exception.status_code,
            404,
        )

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider.id,
                self.retailer.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                99999,
                self.dispatcher.id,
            )

        self.assertEqual(
            context.exception.status_code,
            404,
        )

        invalid_rider_user = self._user(
            "Not A Rider",
            "0711000096",
            UserRole.RETAILER,
        )

        invalid_rider = Rider(
            user=invalid_rider_user
        )

        self.db.add(invalid_rider)
        self.db.commit()

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                invalid_rider.id,
                self.dispatcher.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

    def test_assignment_route_endpoint(self):
        delivery = self._create_sample_delivery()

        request = DeliveryAssignRequest(
            rider_id=self.rider.id,
            dispatcher_id=self.dispatcher.id,
        )

        response = assign_delivery(
            delivery.id,
            request,
            self.db,
            self.dispatcher,
        )

        self.assertEqual(
            response.assigned_rider_id,
            self.rider.id,
        )

        self.assertEqual(
            response.assigned_by,
            self.dispatcher.id,
        )

        self.assertEqual(
            response.status,
            DeliveryStatus.ASSIGNED,
        )

    def test_assignment_rejects_user_id_without_rider_record(
        self,
    ):
        delivery = self._create_sample_delivery()

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider.user_id,
                self.dispatcher.id,
            )

        self.assertEqual(
            context.exception.status_code,
            404,
        )

    def test_assignment_rejects_invalid_roles_and_states(
        self,
    ):
        delivery = self._create_sample_delivery()

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider.id,
                self.retailer.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

        assign_delivery_to_rider(
            self.db,
            delivery.id,
            self.rider.id,
            self.dispatcher.id,
        )

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider.id,
                self.dispatcher.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

    def test_assignment_rejects_unavailable_rider(self):
        delivery = self._create_sample_delivery(
            self.retailer.id,
            "Unavailable rider test",
        )

        self.rider.availability_status = "BUSY"
        self.db.commit()

        with self.assertRaises(HTTPException) as context:
            assign_delivery_to_rider(
                self.db,
                delivery.id,
                self.rider.id,
                self.dispatcher.id,
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )

        self.assertIn(
            "not available",
            context.exception.detail.lower(),
        )

    def test_delivery_filters_use_authoritative_columns(self):
        open_delivery = self._create_sample_delivery(
            self.retailer.id,
            "Open",
        )

        assigned_delivery = self._create_sample_delivery(
            self.retailer2.id,
            "Assigned",
        )

        assign_delivery_to_rider(
            self.db,
            assigned_delivery.id,
            self.rider.id,
            self.dispatcher.id,
        )

        self.assertEqual(
            list_delivery_records(
                self.db,
                retailer_id=self.retailer.id,
            ),
            [open_delivery],
        )

        self.assertEqual(
            list_delivery_records(
                self.db,
                rider_id=self.rider.id,
            ),
            [assigned_delivery],
        )

        self.assertEqual(
            list_delivery_records(
                self.db,
                dispatcher_id=self.dispatcher.id,
            ),
            [assigned_delivery],
        )

    def _filtering_dataset(self):
        open_one = self._create_sample_delivery(
            self.retailer.id,
            "Open one",
        )

        open_two = self._create_sample_delivery(
            self.retailer2.id,
            "Open two",
        )

        assigned_one = self._create_sample_delivery(
            self.retailer.id,
            "Assigned one",
        )

        assign_delivery_to_rider(
            self.db,
            assigned_one.id,
            self.rider.id,
            self.dispatcher.id,
        )

        delivered = self._create_sample_delivery(
            self.retailer2.id,
            "Delivered",
        )

        assign_delivery_to_rider(
            self.db,
            delivered.id,
            self.rider2.id,
            self.dispatcher2.id,
        )

        validate_and_apply_status_transition(
            self.db,
            delivered,
            DeliveryStatus.PICKED_UP,
            self.rider2.user_id,
        )

        validate_and_apply_status_transition(
            self.db,
            delivered,
            DeliveryStatus.DELIVERED,
            self.rider2.user_id,
        )

        return (
            open_one,
            open_two,
            assigned_one,
            delivered,
        )

    def test_list_deliveries_no_filter(self):
        deliveries = self._filtering_dataset()

        self.assertEqual(
            len(list_delivery_records(self.db)),
            len(deliveries),
        )

    def test_list_deliveries_filter_by_status(self):
        (
            open_one,
            open_two,
            assigned_one,
            delivered,
        ) = self._filtering_dataset()

        self.assertEqual(
            {
                delivery.id
                for delivery in list_delivery_records(
                    self.db,
                    status=DeliveryStatus.OPEN,
                )
            },
            {
                open_one.id,
                open_two.id,
            },
        )

        self.assertEqual(
            [
                delivery.id
                for delivery in list_delivery_records(
                    self.db,
                    status=DeliveryStatus.DELIVERED,
                )
            ],
            [delivered.id],
        )

    def test_list_deliveries_combined_filters(self):
        (
            open_one,
            open_two,
            assigned_one,
            delivered,
        ) = self._filtering_dataset()

        results = list_delivery_records(
            self.db,
            status=DeliveryStatus.ASSIGNED,
            retailer_id=self.retailer.id,
            rider_id=self.rider.id,
        )

        self.assertEqual(
            [delivery.id for delivery in results],
            [assigned_one.id],
        )

        self.assertEqual(
            list_delivery_records(
                self.db,
                retailer_id=self.retailer.id,
                rider_id=self.rider2.id,
            ),
            [],
        )

    def test_list_deliveries_route_query_parameters(self):
        (
            open_one,
            open_two,
            assigned_one,
            delivered,
        ) = self._filtering_dataset()

        results = list_deliveries(
            status=DeliveryStatus.ASSIGNED,
            rider_id=self.rider.id,
            retailer_id=None,
            dispatcher_id=None,
            db=self.db,
            current_user=self.rider.user,
        )

        self.assertEqual(
            [delivery.id for delivery in results],
            [assigned_one.id],
        )

    def test_assignment_schema_keeps_dispatcher_api_name(self):
        request = DeliveryAssignRequest(
            rider_id=self.rider.id,
            dispatcher_id=self.dispatcher.id,
        )

        self.assertEqual(
            request.rider_id,
            self.rider.id,
        )

        self.assertEqual(
            request.dispatcher_id,
            self.dispatcher.id,
        )


if __name__ == "__main__":
    unittest.main()