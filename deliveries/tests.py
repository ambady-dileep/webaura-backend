from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from orders.models import Address, Order, OrderStatus
from restaurants.models import Category, FoodItem, Restaurant

from .models import Delivery, DeliveryStatus, InvalidDeliveryTransition


# ---------------------------------------------------------------------------
# Model-level tests: Delivery.transition_to() state machine
# ---------------------------------------------------------------------------

class DeliveryTransitionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="dlv_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="dlv_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Delivery Place", address="X"
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            delivery_address=self.address,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )
        self.delivery = Delivery.objects.create(order=self.order)

    def test_default_status_is_unassigned(self):
        self.assertEqual(self.delivery.status, DeliveryStatus.UNASSIGNED)

    def test_valid_forward_transition_succeeds(self):
        self.delivery.transition_to(DeliveryStatus.ASSIGNED)
        self.assertEqual(self.delivery.status, DeliveryStatus.ASSIGNED)
        self.assertIsNotNone(self.delivery.assigned_at)

    def test_full_happy_path_sequence(self):
        self.delivery.transition_to(DeliveryStatus.ASSIGNED)
        self.delivery.transition_to(DeliveryStatus.PICKED_UP)
        self.assertIsNotNone(self.delivery.picked_up_at)
        self.delivery.transition_to(DeliveryStatus.OUT_FOR_DELIVERY)
        self.delivery.transition_to(DeliveryStatus.DELIVERED)
        self.assertEqual(self.delivery.status, DeliveryStatus.DELIVERED)
        self.assertIsNotNone(self.delivery.delivered_at)

    def test_skipping_a_state_is_rejected(self):
        with self.assertRaises(InvalidDeliveryTransition):
            self.delivery.transition_to(DeliveryStatus.PICKED_UP)  # skips ASSIGNED

    def test_moving_backward_is_rejected(self):
        self.delivery.transition_to(DeliveryStatus.ASSIGNED)
        self.delivery.transition_to(DeliveryStatus.PICKED_UP)
        with self.assertRaises(InvalidDeliveryTransition):
            self.delivery.transition_to(DeliveryStatus.ASSIGNED)

    def test_delivered_is_terminal(self):
        self.delivery.transition_to(DeliveryStatus.ASSIGNED)
        self.delivery.transition_to(DeliveryStatus.PICKED_UP)
        self.delivery.transition_to(DeliveryStatus.OUT_FOR_DELIVERY)
        self.delivery.transition_to(DeliveryStatus.DELIVERED)
        with self.assertRaises(InvalidDeliveryTransition):
            self.delivery.transition_to(DeliveryStatus.OUT_FOR_DELIVERY)


# ---------------------------------------------------------------------------
# API-level tests: POST /api/orders/{id}/assign-delivery/
# ---------------------------------------------------------------------------

class AssignDeliveryAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="assign_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="assign_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.admin = User.objects.create_user(
            username="assign_admin", password="StrongPass123!", role=Role.ADMIN
        )
        self.partner = User.objects.create_user(
            username="assign_partner", password="StrongPass123!", role=Role.DELIVERY_PARTNER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Assign Place", address="X"
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            delivery_address=self.address,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            status=OrderStatus.ACCEPTED,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _assign(self, order=None, partner_id=None):
        order = order or self.order
        body = {} if partner_id is None else {"delivery_partner_id": partner_id}
        return self.client.post(f"/api/orders/{order.id}/assign-delivery/", body, format="json")

    def test_admin_can_assign_delivery_for_accepted_order(self):
        response = self._assign(partner_id=self.partner.id)
        self.assertEqual(response.status_code, 201)
        delivery = Delivery.objects.get(order=self.order)
        self.assertEqual(delivery.delivery_partner, self.partner)
        self.assertEqual(delivery.status, DeliveryStatus.ASSIGNED)

    def test_admin_can_assign_without_specifying_partner(self):
        response = self._assign()
        self.assertEqual(response.status_code, 201)
        delivery = Delivery.objects.get(order=self.order)
        self.assertEqual(delivery.delivery_partner, self.partner)

    def test_assignment_fails_when_no_partner_available(self):
        # Make the only partner busy with another non-terminal delivery.
        other_order = Order.objects.create(
            customer=self.customer, restaurant=self.restaurant,
            delivery_address=self.address, subtotal=Decimal("50.00"),
            total_amount=Decimal("50.00"), status=OrderStatus.ACCEPTED,
        )
        Delivery.objects.create(
            order=other_order, delivery_partner=self.partner, status=DeliveryStatus.ASSIGNED
        )
        response = self._assign()
        self.assertEqual(response.status_code, 400)

    def test_cannot_assign_delivery_for_non_accepted_order(self):
        self.order.status = OrderStatus.PLACED
        self.order.save()
        response = self._assign(partner_id=self.partner.id)
        self.assertEqual(response.status_code, 400)

    def test_cannot_double_assign_same_order(self):
        self._assign(partner_id=self.partner.id)
        response = self._assign(partner_id=self.partner.id)
        self.assertEqual(response.status_code, 400)

    def test_non_admin_cannot_assign_delivery(self):
        self.client.force_authenticate(user=self.customer)
        response = self._assign(partner_id=self.partner.id)
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# API-level tests: GET /api/deliveries/ and PATCH /api/deliveries/{id}/status/
# ---------------------------------------------------------------------------

class DeliveryStatusUpdateAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="status_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="status_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.admin = User.objects.create_user(
            username="status_admin", password="StrongPass123!", role=Role.ADMIN
        )
        self.partner = User.objects.create_user(
            username="status_partner", password="StrongPass123!", role=Role.DELIVERY_PARTNER
        )
        self.other_partner = User.objects.create_user(
            username="status_other_partner", password="StrongPass123!", role=Role.DELIVERY_PARTNER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Status Place", address="X"
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            delivery_address=self.address,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            status=OrderStatus.ACCEPTED,
        )
        self.delivery = Delivery.objects.create(
            order=self.order, delivery_partner=self.partner, status=DeliveryStatus.ASSIGNED
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.partner)

    def _patch_status(self, new_status):
        return self.client.patch(
            f"/api/deliveries/{self.delivery.id}/status/", {"status": new_status}, format="json"
        )

    def test_assigned_partner_can_advance_status(self):
        response = self._patch_status(DeliveryStatus.PICKED_UP)
        self.assertEqual(response.status_code, 200)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, DeliveryStatus.PICKED_UP)

    def test_other_partner_gets_403(self):
        self.client.force_authenticate(user=self.other_partner)
        response = self._patch_status(DeliveryStatus.PICKED_UP)
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_patch_delivery_status(self):
        self.client.force_authenticate(user=self.customer)
        response = self._patch_status(DeliveryStatus.PICKED_UP)
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_patch_delivery_status(self):
        # Spec: admins are read/assign only; only the assigned partner
        # drives the delivery state machine.
        self.client.force_authenticate(user=self.admin)
        response = self._patch_status(DeliveryStatus.PICKED_UP)
        self.assertEqual(response.status_code, 403)

    def test_skipping_a_state_returns_400(self):
        response = self._patch_status(DeliveryStatus.DELIVERED)
        self.assertEqual(response.status_code, 400)

    def test_moving_backward_returns_400(self):
        self._patch_status(DeliveryStatus.PICKED_UP)
        response = self._patch_status(DeliveryStatus.ASSIGNED)
        self.assertEqual(response.status_code, 400)

    def test_invalid_status_value_returns_400(self):
        response = self._patch_status("not_a_real_status")
        self.assertEqual(response.status_code, 400)

    def test_delivery_partner_sees_only_own_assignments(self):
        other_order = Order.objects.create(
            customer=self.customer, restaurant=self.restaurant,
            delivery_address=self.address, subtotal=Decimal("50.00"),
            total_amount=Decimal("50.00"), status=OrderStatus.ACCEPTED,
        )
        Delivery.objects.create(
            order=other_order, delivery_partner=self.other_partner,
            status=DeliveryStatus.ASSIGNED,
        )
        response = self.client.get("/api/deliveries/")
        self.assertEqual(response.status_code, 200)
        returned_ids = {d["id"] for d in response.data["results"]} if isinstance(
            response.data, dict) and "results" in response.data else {d["id"] for d in response.data}
        self.assertIn(self.delivery.id, returned_ids)
        self.assertEqual(len(returned_ids), 1)

    def test_admin_sees_all_deliveries(self):
        other_order = Order.objects.create(
            customer=self.customer, restaurant=self.restaurant,
            delivery_address=self.address, subtotal=Decimal("50.00"),
            total_amount=Decimal("50.00"), status=OrderStatus.ACCEPTED,
        )
        Delivery.objects.create(
            order=other_order, delivery_partner=self.other_partner,
            status=DeliveryStatus.ASSIGNED,
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/deliveries/")
        self.assertEqual(response.status_code, 200)
        count = response.data["count"] if isinstance(response.data, dict) and "count" in response.data \
            else len(response.data)
        self.assertEqual(count, 2)