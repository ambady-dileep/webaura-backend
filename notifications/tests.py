from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from orders.models import Address, Order, OrderStatus
from restaurants.models import Category, FoodItem, Restaurant
from .models import Notification
from .tasks import (
    daily_restaurant_sales_summary,
    expire_unaccepted_order,
    send_order_confirmation_notification,
)


# All Celery tasks run synchronously (no worker/broker needed) inside tests.
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class NotificationTaskTestsBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="notif_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="notif_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Notif Place", address="X"
        )
        self.category = Category.objects.create(restaurant=self.restaurant, name="Mains")
        self.food_item = FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category,
            name="Pizza", price=Decimal("250.00"),
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )

    def _create_order(self, **overrides):
        defaults = dict(
            customer=self.customer,
            restaurant=self.restaurant,
            delivery_address=self.address,
            subtotal=Decimal("250.00"),
            total_amount=Decimal("250.00"),
        )
        defaults.update(overrides)
        return Order.objects.create(**defaults)


class OrderConfirmationNotificationTests(NotificationTaskTestsBase):
    def test_creates_notification_for_customer(self):
        order = self._create_order()

        send_order_confirmation_notification.delay(order.id)

        self.assertEqual(Notification.objects.count(), 1)
        notification = Notification.objects.first()
        self.assertEqual(notification.user, self.customer)
        self.assertEqual(notification.order, order)
        self.assertIn(order.order_number, notification.message)

    def test_missing_order_does_not_raise(self):
        # Order.DoesNotExist is caught inside the task — should just return.
        send_order_confirmation_notification.delay(999999)
        self.assertEqual(Notification.objects.count(), 0)

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        NOTIFICATION_SIMULATED_FAILURE_RATE=1.0,
    )
    def test_retries_on_simulated_failure_then_gives_up(self):
        order = self._create_order()

        # With failure_rate=1.0 every attempt fails; eager mode still
        # honors max_retries, so it raises once retries are exhausted
        # instead of hanging or succeeding silently.
        with self.assertRaises(Exception):
            send_order_confirmation_notification.delay(order.id)

        # No notification should have been created — every attempt failed.
        self.assertEqual(Notification.objects.count(), 0)

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        NOTIFICATION_SIMULATED_FAILURE_RATE=0.0,
    )
    def test_succeeds_when_failure_rate_is_zero(self):
        order = self._create_order()
        send_order_confirmation_notification.delay(order.id)
        self.assertEqual(Notification.objects.count(), 1)


class ExpireUnacceptedOrderTests(NotificationTaskTestsBase):
    def test_placed_order_is_cancelled(self):
        order = self._create_order()  # status defaults to PLACED

        expire_unaccepted_order.delay(order.id)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)

    def test_already_accepted_order_is_left_untouched(self):
        order = self._create_order()
        order.transition_to(OrderStatus.ACCEPTED)
        order.save()

        expire_unaccepted_order.delay(order.id)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.ACCEPTED)

    def test_already_rejected_order_is_left_untouched(self):
        order = self._create_order()
        order.transition_to(OrderStatus.REJECTED)
        order.save()

        expire_unaccepted_order.delay(order.id)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.REJECTED)

    def test_missing_order_does_not_raise(self):
        expire_unaccepted_order.delay(999999)  # should just log and return


class DailyRestaurantSalesSummaryTests(NotificationTaskTestsBase):
    def test_creates_summary_notification_for_owner_with_orders_today(self):
        self._create_order(total_amount=Decimal("250.00"))
        self._create_order(total_amount=Decimal("300.00"))

        created_count = daily_restaurant_sales_summary.delay().get()

        self.assertEqual(created_count, 1)
        notification = Notification.objects.get(user=self.owner)
        self.assertIn(self.restaurant.name, notification.message)
        self.assertIn("2 completed order(s)", notification.message)

    def test_excludes_cancelled_and_rejected_from_revenue_but_counts_them(self):
        cancelled = self._create_order(total_amount=Decimal("100.00"))
        cancelled.transition_to(OrderStatus.CANCELLED)
        cancelled.save()

        daily_restaurant_sales_summary.delay()

        notification = Notification.objects.get(user=self.owner)
        self.assertIn("0 completed order(s)", notification.message)
        self.assertIn("1 cancelled/rejected", notification.message)

    def test_restaurant_with_no_activity_today_gets_no_notification(self):
        # No orders created at all for self.restaurant.
        created_count = daily_restaurant_sales_summary.delay().get()

        self.assertEqual(created_count, 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_inactive_restaurant_is_skipped_even_with_orders(self):
        self._create_order()
        self.restaurant.is_active = False
        self.restaurant.save()

        daily_restaurant_sales_summary.delay()

        self.assertEqual(Notification.objects.count(), 0)
        
class NotificationListAPITests(NotificationTaskTestsBase):
    """GET /api/notifications/"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_requires_authentication(self):
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, 401)

    def test_returns_only_the_authenticated_users_notifications(self):
        order = self._create_order()
        Notification.objects.create(
            user=self.customer, order=order, message="Your order is confirmed."
        )
        Notification.objects.create(
            user=self.owner, order=order, message="New order received."
        )

        self.client.force_authenticate(user=self.customer)
        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message"], "Your order is confirmed.")
        self.assertEqual(results[0]["order_number"], order.order_number)

    def test_returns_newest_first(self):
        order = self._create_order()
        first = Notification.objects.create(
            user=self.customer, order=order, message="First"
        )
        second = Notification.objects.create(
            user=self.customer, order=order, message="Second"
        )

        self.client.force_authenticate(user=self.customer)
        response = self.client.get("/api/notifications/")

        results = response.data["results"]
        self.assertEqual(results[0]["id"], second.id)
        self.assertEqual(results[1]["id"], first.id)