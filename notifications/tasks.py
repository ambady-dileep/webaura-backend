import logging
import random
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_order_confirmation_notification(self, order_id):
    """
    Queued via .delay(order.id) from CheckoutView *after* its
    transaction.atomic() block exits successfully — never from inside it,
    so a rolled-back checkout never produces a phantom notification.

    Retry demo: set settings.NOTIFICATION_SIMULATED_FAILURE_RATE to 1.0
    (e.g. via override_settings in a test, or the env var below) and every
    attempt will fail, so you can watch it retry up to 3 times in the
    worker logs before giving up.
    """
    from orders.models import Order
    from .models import Notification

    try:
        order = Order.objects.select_related("customer", "restaurant").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning("send_order_confirmation_notification: order %s no longer exists", order_id)
        return

    failure_rate = getattr(settings, "NOTIFICATION_SIMULATED_FAILURE_RATE", 0)
    if failure_rate and random.random() < failure_rate:
        logger.warning(
            "send_order_confirmation_notification: simulated failure for order %s (attempt %s/%s)",
            order.order_number, self.request.retries + 1, self.max_retries,
        )
        raise self.retry(exc=RuntimeError("Simulated notification delivery failure"))

    with transaction.atomic():
        Notification.objects.create(
            user=order.customer,
            order=order,
            message=(
                f"Your order {order.order_number} from {order.restaurant.name} "
                f"has been placed successfully. Total: {order.total_amount}."
            ),
        )

    logger.info("Order confirmation notification created for order %s", order.order_number)


@shared_task
def expire_unaccepted_order(order_id):
    """
    Scheduled with .apply_async(args=[order.id], countdown=300) right after
    order creation. Re-fetches the order from the DB — never trusts a
    stale in-memory copy — and only cancels it if it's STILL PLACED.
    """
    from orders.models import Order, OrderStatus, InvalidStatusTransition

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            if order.status != OrderStatus.PLACED:
                logger.info(
                    "expire_unaccepted_order: order %s is '%s', not PLACED — skipping.",
                    order.order_number, order.status,
                )
                return
            order.transition_to(OrderStatus.CANCELLED)
            order.save()
            logger.info(
                "expire_unaccepted_order: order %s auto-cancelled after 5 minutes.",
                order.order_number,
            )
    except Order.DoesNotExist:
        logger.warning("expire_unaccepted_order: order %s no longer exists", order_id)
    except InvalidStatusTransition as e:
        logger.warning("expire_unaccepted_order: could not cancel order %s: %s", order_id, e)


@shared_task
def daily_restaurant_sales_summary():
    """
    4th task (chosen: daily sales summary). Scheduled nightly via
    CELERY_BEAT_SCHEDULE in settings.py. Aggregates today's orders per
    restaurant and drops a Notification for each owner.
    """
    from orders.models import Order, OrderStatus
    from restaurants.models import Restaurant
    from .models import Notification

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    created = 0
    for restaurant in Restaurant.objects.filter(is_active=True):
        todays_orders = Order.objects.filter(
            restaurant=restaurant, created_at__gte=today_start, created_at__lt=today_end,
        )
        revenue_orders = todays_orders.exclude(
            status__in=[OrderStatus.CANCELLED, OrderStatus.REJECTED]
        )
        stats = revenue_orders.aggregate(
            total_revenue=Sum("total_amount"), order_count=Count("id")
        )
        cancelled_count = todays_orders.filter(
            status__in=[OrderStatus.CANCELLED, OrderStatus.REJECTED]
        ).count()

        total_revenue = stats["total_revenue"] or 0
        order_count = stats["order_count"] or 0

        if order_count == 0 and cancelled_count == 0:
            continue

        Notification.objects.create(
            user=restaurant.owner,
            order=None,
            message=(
                f"Daily summary for {restaurant.name} ({today_start:%Y-%m-%d}): "
                f"{order_count} completed order(s) totalling {total_revenue}, "
                f"{cancelled_count} cancelled/rejected."
            ),
        )
        created += 1

    logger.info("daily_restaurant_sales_summary: created %s notification(s).", created)
    return created