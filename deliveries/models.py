from django.conf import settings
from django.db import models
from django.utils import timezone


class InvalidDeliveryTransition(Exception):
    """Raised when Delivery.transition_to() is called with a status that
    isn't reachable from the delivery's current status."""

    pass


class DeliveryStatus(models.TextChoices):
    UNASSIGNED = "unassigned", "Unassigned"
    ASSIGNED = "assigned", "Assigned"
    PICKED_UP = "picked_up", "Picked Up"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
    DELIVERED = "delivered", "Delivered"


class Delivery(models.Model):
    order = models.OneToOneField(
        "orders.Order", on_delete=models.CASCADE, related_name="delivery"
    )
    delivery_partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
    )
    status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.UNASSIGNED,
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Forward-only, same explicit-map pattern as Order.ALLOWED_TRANSITIONS
    # in orders/models.py — any transition not listed here is rejected,
    # so a delivery can never skip a state or move backward.
    ALLOWED_TRANSITIONS = {
        DeliveryStatus.UNASSIGNED: {DeliveryStatus.ASSIGNED},
        DeliveryStatus.ASSIGNED: {DeliveryStatus.PICKED_UP},
        DeliveryStatus.PICKED_UP: {DeliveryStatus.OUT_FOR_DELIVERY},
        DeliveryStatus.OUT_FOR_DELIVERY: {DeliveryStatus.DELIVERED},
        DeliveryStatus.DELIVERED: set(),
    }

    def transition_to(self, new_status):
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise InvalidDeliveryTransition(
                f"Cannot transition delivery for order "
                f"{self.order.order_number} from '{self.status}' to "
                f"'{new_status}'."
            )
        self.status = new_status
        now = timezone.now()
        if new_status == DeliveryStatus.ASSIGNED:
            self.assigned_at = now
        elif new_status == DeliveryStatus.PICKED_UP:
            self.picked_up_at = now
        elif new_status == DeliveryStatus.DELIVERED:
            self.delivered_at = now
        return self

    def __str__(self):
        return f"Delivery({self.order.order_number}, {self.status})"