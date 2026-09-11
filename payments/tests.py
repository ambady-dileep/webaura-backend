from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from orders.models import Address, Order
from restaurants.models import Category, FoodItem, Restaurant

from .models import Payment


class MockPaymentAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="pay_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="pay_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.other_customer = User.objects.create_user(
            username="pay_other_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Payment Place", address="X"
        )
        self.category = Category.objects.create(restaurant=self.restaurant, name="Mains")
        self.food_item = FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category,
            name="Burger", price=Decimal("150.00"),
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            delivery_address=self.address,
            subtotal=Decimal("150.00"),
            total_amount=Decimal("150.00"),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.customer)

    def _pay(self, order=None, success=None):
        order = order or self.order
        body = {} if success is None else {"success": success}
        return self.client.post(f"/api/payments/{order.id}/mock/", body, format="json")

    def test_successful_payment_sets_status_success(self):
        response = self._pay(success=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Payment.Status.SUCCESS)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.SUCCESS)

    def test_failed_payment_sets_status_failed(self):
        response = self._pay(success=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Payment.Status.FAILED)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.FAILED)

    def test_success_defaults_to_true_when_body_omitted(self):
        response = self._pay(success=None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Payment.Status.SUCCESS)

    def test_payment_row_is_created_on_first_call(self):
        self.assertFalse(Payment.objects.filter(order=self.order).exists())
        self._pay(success=True)
        self.assertTrue(Payment.objects.filter(order=self.order).exists())

    def test_payment_amount_matches_order_total(self):
        self._pay(success=True)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.amount, self.order.total_amount)

    def test_calling_again_after_success_does_not_flip_to_failed(self):
        first = self._pay(success=True)
        self.assertEqual(first.status_code, 200)
        second = self._pay(success=False)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["status"], Payment.Status.SUCCESS)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.SUCCESS)

    def test_retrying_after_failure_can_still_succeed(self):
        self._pay(success=False)
        second = self._pay(success=True)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["status"], Payment.Status.SUCCESS)

    def test_pending_payment_is_never_treated_as_paid(self):
        # No mock payment call yet -> no Payment row exists, so nothing
        # downstream should consider this order paid.
        self.assertFalse(
            Payment.objects.filter(order=self.order, status=Payment.Status.SUCCESS).exists()
        )

    def test_customer_cannot_pay_for_another_customers_order(self):
        self.client.force_authenticate(user=self.other_customer)
        response = self._pay(success=True)
        self.assertEqual(response.status_code, 404)

    def test_restaurant_owner_cannot_use_mock_payment_endpoint(self):
        self.client.force_authenticate(user=self.owner)
        response = self._pay(success=True)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_cannot_use_mock_payment_endpoint(self):
        self.client.force_authenticate(user=None)
        response = self._pay(success=True)
        self.assertIn(response.status_code, (401, 403))

    def test_nonexistent_order_returns_404(self):
        response = self.client.post("/api/payments/999999/mock/", {"success": True}, format="json")
        self.assertEqual(response.status_code, 404)