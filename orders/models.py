import random
import string
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_order_number():
    """
    Generates a unique, human-readable order number like ORD-20260911-A1B2C.
    Retries a few times on the rare chance of a collision before widening
    the random suffix.
    """
    date_part = timezone.now().strftime("%Y%m%d")
    for _ in range(5):
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        candidate = f"ORD-{date_part}-{suffix}"
        if not Order.objects.filter(order_number=candidate).exists():
            return candidate
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"ORD-{date_part}-{suffix}"


class Address(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses"
    )
    label = models.CharField(max_length=50, blank=True)
    full_address = models.TextField()
    city = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    phone_number = models.CharField(max_length=15)

    def __str__(self):
        return f"{self.label or 'Address'} — {self.customer.username}"

class InvalidStatusTransition(Exception):
    """Raised when Order.transition_to() is called with a status that isn't
    reachable from the order's current status."""
    pass

class OrderStatus(models.TextChoices):
    PLACED = "placed", "Placed"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    PREPARING = "preparing", "Preparing"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class Order(models.Model):
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    restaurant = models.ForeignKey(
        "restaurants.Restaurant", on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PLACED
    )
    delivery_address = models.ForeignKey(
        Address, on_delete=models.PROTECT, related_name="orders"
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    delivery_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Coupon FK intentionally omitted — Module 4 hasn't been built yet.
    # NOTE: no field-level unique=True anymore — see Meta.unique_together below.
    idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    ALLOWED_TRANSITIONS = {
        OrderStatus.PLACED: {OrderStatus.ACCEPTED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
        OrderStatus.ACCEPTED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
        OrderStatus.PREPARING: {OrderStatus.OUT_FOR_DELIVERY},
        OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
        OrderStatus.DELIVERED: set(),
        OrderStatus.REJECTED: set(),
        OrderStatus.CANCELLED: set(),
    }

    def transition_to(self, new_status):
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise InvalidStatusTransition(
                f"Cannot transition order {self.order_number} "
                f"from '{self.status}' to '{new_status}'."
            )
        self.status = new_status
        return self

    class Meta:
        # A given customer can't reuse the same idempotency key across two
        # DIFFERENT orders, but two different customers can safely use the
        # same key string without colliding.
        unique_together = ("customer", "idempotency_key")
        indexes = [
            models.Index(fields=["restaurant", "status"]),
            models.Index(fields=["customer", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = generate_order_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey(
        "restaurants.FoodItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    # Snapshots — preserve historical truth even if the FoodItem changes
    # price or is deleted later.
    food_item_name = models.CharField(max_length=255)
    price_at_purchase = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} x {self.food_item_name} ({self.order.order_number})"

    @property
    def line_total(self):
        return self.price_at_purchase * self.quantity