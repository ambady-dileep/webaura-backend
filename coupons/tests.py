from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from orders.models import Address, Order
from payments.models import Payment
from restaurants.models import Category, FoodItem, Restaurant

from .models import Coupon, CouponError, validate_coupon


def make_coupon(**overrides):
    defaults = dict(
        code="WELCOME50",
        discount_type=Coupon.DiscountType.FLAT,
        value=Decimal("50.00"),
        min_order_amount=Decimal("0.00"),
        max_discount_amount=None,
        expiry_date=timezone.now() + timedelta(days=1),
        usage_limit=10,
        times_used=0,
    )
    defaults.update(overrides)
    return Coupon.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Model-level tests: Coupon.compute_discount() and validate_coupon()
# ---------------------------------------------------------------------------

class CouponComputeDiscountTests(TestCase):
    def test_flat_discount_returns_flat_value(self):
        coupon = make_coupon(discount_type=Coupon.DiscountType.FLAT, value=Decimal("50.00"))
        self.assertEqual(coupon.compute_discount(Decimal("500.00")), Decimal("50.00"))

    def test_flat_discount_never_exceeds_subtotal(self):
        coupon = make_coupon(discount_type=Coupon.DiscountType.FLAT, value=Decimal("500.00"))
        self.assertEqual(coupon.compute_discount(Decimal("100.00")), Decimal("100.00"))

    def test_percentage_discount_is_computed_correctly(self):
        coupon = make_coupon(
            discount_type=Coupon.DiscountType.PERCENTAGE, value=Decimal("10.00")
        )
        self.assertEqual(coupon.compute_discount(Decimal("200.00")), Decimal("20.00"))

    def test_percentage_discount_capped_by_max_discount_amount(self):
        coupon = make_coupon(
            discount_type=Coupon.DiscountType.PERCENTAGE,
            value=Decimal("50.00"),
            max_discount_amount=Decimal("30.00"),
        )
        # 50% of 200 = 100, but capped at 30.
        self.assertEqual(coupon.compute_discount(Decimal("200.00")), Decimal("30.00"))

    def test_percentage_discount_uncapped_when_max_discount_amount_is_none(self):
        coupon = make_coupon(
            discount_type=Coupon.DiscountType.PERCENTAGE,
            value=Decimal("50.00"),
            max_discount_amount=None,
        )
        self.assertEqual(coupon.compute_discount(Decimal("200.00")), Decimal("100.00"))


class ValidateCouponTests(TestCase):
    def test_valid_coupon_raises_nothing(self):
        coupon = make_coupon()
        try:
            validate_coupon(coupon, Decimal("100.00"))
        except CouponError:
            self.fail("validate_coupon() raised CouponError for a valid coupon")

    def test_expired_coupon_raises_expired_code(self):
        coupon = make_coupon(expiry_date=timezone.now() - timedelta(days=1))
        with self.assertRaises(CouponError) as ctx:
            validate_coupon(coupon, Decimal("100.00"))
        self.assertEqual(ctx.exception.code, "expired")

    def test_exhausted_coupon_raises_usage_limit_reached_code(self):
        coupon = make_coupon(usage_limit=5, times_used=5)
        with self.assertRaises(CouponError) as ctx:
            validate_coupon(coupon, Decimal("100.00"))
        self.assertEqual(ctx.exception.code, "usage_limit_reached")

    def test_below_minimum_order_raises_below_minimum_code(self):
        coupon = make_coupon(min_order_amount=Decimal("500.00"))
        with self.assertRaises(CouponError) as ctx:
            validate_coupon(coupon, Decimal("100.00"))
        self.assertEqual(ctx.exception.code, "below_minimum_order_amount")

    def test_checks_run_in_order_expired_then_usage_then_minimum(self):
        # Expired AND exhausted AND below minimum at once — expired should
        # win, since validate_coupon() checks expiry first.
        coupon = make_coupon(
            expiry_date=timezone.now() - timedelta(days=1),
            usage_limit=1,
            times_used=1,
            min_order_amount=Decimal("999.00"),
        )
        with self.assertRaises(CouponError) as ctx:
            validate_coupon(coupon, Decimal("1.00"))
        self.assertEqual(ctx.exception.code, "expired")

        # Not expired, but exhausted AND below minimum — usage_limit wins.
        coupon2 = make_coupon(
            code="OTHER",
            expiry_date=timezone.now() + timedelta(days=1),
            usage_limit=1,
            times_used=1,
            min_order_amount=Decimal("999.00"),
        )
        with self.assertRaises(CouponError) as ctx2:
            validate_coupon(coupon2, Decimal("1.00"))
        self.assertEqual(ctx2.exception.code, "usage_limit_reached")


# ---------------------------------------------------------------------------
# API-level tests: POST /api/orders/{id}/coupon/
# ---------------------------------------------------------------------------

class ApplyCouponAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="coupon_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="coupon_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.other_customer = User.objects.create_user(
            username="coupon_other_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Coupon Place", address="X"
        )
        self.category = Category.objects.create(restaurant=self.restaurant, name="Mains")
        self.food_item = FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category,
            name="Pizza", price=Decimal("200.00"),
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            delivery_address=self.address,
            subtotal=Decimal("200.00"),
            total_amount=Decimal("200.00"),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.customer)

    def _apply(self, code, order=None):
        order = order or self.order
        return self.client.post(f"/api/orders/{order.id}/coupon/", {"code": code}, format="json")

    def test_applying_valid_coupon_updates_order_totals(self):
        make_coupon(code="SAVE20", discount_type=Coupon.DiscountType.FLAT, value=Decimal("20.00"))
        response = self._apply("SAVE20")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.discount_amount, Decimal("20.00"))
        self.assertEqual(self.order.total_amount, Decimal("180.00"))
        self.assertEqual(self.order.coupon.code, "SAVE20")

    def test_applying_coupon_increments_times_used(self):
        coupon = make_coupon(code="SAVE20", value=Decimal("20.00"))
        self._apply("SAVE20")
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 1)

    def test_coupon_code_lookup_is_case_insensitive(self):
        make_coupon(code="SAVE20", value=Decimal("20.00"))
        response = self._apply("save20")
        self.assertEqual(response.status_code, 200)

    def test_unknown_coupon_code_returns_400_not_found(self):
        response = self._apply("DOESNOTEXIST")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "not_found")

    def test_expired_coupon_returns_400_expired(self):
        make_coupon(code="OLD10", expiry_date=timezone.now() - timedelta(days=1))
        response = self._apply("OLD10")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "expired")

    def test_exhausted_coupon_returns_400_usage_limit_reached(self):
        make_coupon(code="USEDUP", usage_limit=1, times_used=1)
        response = self._apply("USEDUP")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "usage_limit_reached")

    def test_below_minimum_order_returns_400_below_minimum(self):
        make_coupon(code="BIGORDER", min_order_amount=Decimal("500.00"))
        response = self._apply("BIGORDER")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "below_minimum_order_amount")

    def test_reapplying_a_coupon_to_same_order_is_rejected(self):
        make_coupon(code="ONE", value=Decimal("10.00"))
        make_coupon(code="TWO", value=Decimal("10.00"))
        first = self._apply("ONE")
        self.assertEqual(first.status_code, 200)
        second = self._apply("TWO")
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data["code"], "coupon_already_applied")

    def test_coupon_cannot_be_applied_to_non_placed_order(self):
        self.order.status = "accepted"
        self.order.save()
        make_coupon(code="SAVE20", value=Decimal("20.00"))
        response = self._apply("SAVE20")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "order_not_placed")

    def test_coupon_cannot_be_applied_to_already_paid_order(self):
        Payment.objects.create(
            order=self.order, status=Payment.Status.SUCCESS, amount=self.order.total_amount
        )
        make_coupon(code="SAVE20", value=Decimal("20.00"))
        response = self._apply("SAVE20")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "order_already_paid")

    def test_discount_survives_coupon_being_deleted_afterward(self):
        coupon = make_coupon(code="SAVE20", value=Decimal("20.00"))
        self._apply("SAVE20")
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_amount, Decimal("180.00"))

        coupon.delete()  # coupon FK is SET_NULL

        self.order.refresh_from_db()
        self.assertIsNone(self.order.coupon)
        self.assertEqual(self.order.discount_amount, Decimal("20.00"))
        self.assertEqual(self.order.total_amount, Decimal("180.00"))

    def test_discount_survives_coupon_being_edited_afterward(self):
        coupon = make_coupon(code="SAVE20", value=Decimal("20.00"))
        self._apply("SAVE20")
        self.order.refresh_from_db()

        coupon.value = Decimal("999.00")
        coupon.save()

        self.order.refresh_from_db()
        self.assertEqual(self.order.discount_amount, Decimal("20.00"))
        self.assertEqual(self.order.total_amount, Decimal("180.00"))

    def test_customer_cannot_apply_coupon_to_another_customers_order(self):
        make_coupon(code="SAVE20", value=Decimal("20.00"))
        self.client.force_authenticate(user=self.other_customer)
        response = self._apply("SAVE20")
        self.assertEqual(response.status_code, 404)

    def test_restaurant_owner_cannot_apply_coupon(self):
        make_coupon(code="SAVE20", value=Decimal("20.00"))
        self.client.force_authenticate(user=self.owner)
        response = self._apply("SAVE20")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_cannot_apply_coupon(self):
        make_coupon(code="SAVE20", value=Decimal("20.00"))
        self.client.force_authenticate(user=None)
        response = self._apply("SAVE20")
        self.assertIn(response.status_code, (401, 403))