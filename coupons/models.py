from decimal import Decimal

from django.db import models
from django.utils import timezone


class CouponError(Exception):
    """
    Raised by validate_coupon() when a coupon fails one of the apply-time
    checks. `code` is a short machine-readable reason so callers (and
    tests) can distinguish *why* a coupon was rejected instead of getting
    one generic "invalid coupon" message for every case.
    """

    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        FLAT = "flat", "Flat"
        PERCENTAGE = "percentage", "Percentage"

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=8, decimal_places=2)
    min_order_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    max_discount_amount = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    expiry_date = models.DateTimeField()
    usage_limit = models.PositiveIntegerField()
    times_used = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.code

    def is_expired(self):
        return self.expiry_date <= timezone.now()

    def is_exhausted(self):
        return self.times_used >= self.usage_limit

    def compute_discount(self, subtotal):
        """
        Compute the discount amount this coupon produces for a given
        order subtotal. Does NOT check validity (expiry/usage/minimum) —
        call validate_coupon() first. Percentage discounts are capped by
        max_discount_amount when set, and no coupon can ever discount
        more than the subtotal itself.
        """
        if self.discount_type == self.DiscountType.FLAT:
            discount = self.value
        else:
            discount = (subtotal * self.value / Decimal("100")).quantize(
                Decimal("0.01")
            )
            if self.max_discount_amount is not None:
                discount = min(discount, self.max_discount_amount)
        return min(discount, subtotal)


def validate_coupon(coupon, subtotal):
    """
    Runs the apply-time checks in the exact order the spec calls for:
    expired -> usage limit -> minimum order amount. Raises CouponError
    with a distinct `code` for whichever check fails first, so the API
    can return a specific reason instead of a generic rejection.
    """
    if coupon.is_expired():
        raise CouponError("expired", "This coupon has expired.")
    if coupon.is_exhausted():
        raise CouponError(
            "usage_limit_reached", "This coupon has reached its usage limit."
        )
    if subtotal < coupon.min_order_amount:
        raise CouponError(
            "below_minimum_order_amount",
            f"Order subtotal must be at least {coupon.min_order_amount} "
            f"to use this coupon.",
        )