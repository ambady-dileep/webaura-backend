from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCustomer
from orders.models import Order, OrderStatus
from orders.serializers import OrderSerializer
from payments.models import Payment

from .models import Coupon, CouponError, validate_coupon
from .serializers import ApplyCouponSerializer


class ApplyCouponView(APIView):
    """
    POST /api/orders/{id}/coupon/  — customer, own order only.

    An order can only have a coupon applied while it's still PLACED and
    has not been paid for yet (Payment.status == 'success' is checked,
    not the order status, per the "Payment is the single source of
    truth" rule from the spec). Re-applying to an order that already has
    a coupon is rejected outright — this is also what protects
    Coupon.times_used from being incremented twice by a retried request.
    """

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related("customer", "restaurant", "coupon"),
            pk=pk,
            customer=request.user,
        )

        if order.status != OrderStatus.PLACED:
            return Response(
                {
                    "detail": "Coupons can only be applied to an order that "
                    "is still PLACED.",
                    "code": "order_not_placed",
                },
                status=400,
            )

        if Payment.objects.filter(order=order, status=Payment.Status.SUCCESS).exists():
            return Response(
                {
                    "detail": "This order has already been paid for.",
                    "code": "order_already_paid",
                },
                status=400,
            )

        if order.coupon_id:
            return Response(
                {
                    "detail": "This order already has a coupon applied.",
                    "code": "coupon_already_applied",
                },
                status=400,
            )

        serializer = ApplyCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"].strip()

        try:
            coupon = Coupon.objects.get(code__iexact=code)
        except Coupon.DoesNotExist:
            return Response(
                {"detail": "Coupon not found.", "code": "not_found"}, status=400
            )

        try:
            validate_coupon(coupon, order.subtotal)
        except CouponError as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=400)

        with transaction.atomic():
            # Re-fetch and lock the order row so a concurrent checkout-side
            # update (or a second racing apply-coupon call) can't clobber
            # this. Guard the "already applied" check again inside the
            # lock — the earlier check above is just a fast, un-locked
            # pre-check for a friendlier error on the common path.
            order = Order.objects.select_for_update().get(pk=order.pk)
            if order.coupon_id:
                return Response(
                    {
                        "detail": "This order already has a coupon applied.",
                        "code": "coupon_already_applied",
                    },
                    status=400,
                )

            discount = coupon.compute_discount(order.subtotal)
            order.coupon = coupon
            order.discount_amount = discount
            order.total_amount = (
                order.subtotal + order.delivery_fee + order.tax_amount - discount
            )
            order.save()

            # Increment usage only once we've committed the coupon to this
            # specific order — the coupon_id guard above stops a retried
            # request from double-counting the same order.
            Coupon.objects.filter(pk=coupon.pk).update(times_used=F("times_used") + 1)

        # refresh_from_db() would clear the select_related above and bring
        # back an N+1 on serialization (customer/restaurant/coupon/items
        # would each re-query lazily) — re-fetch with the same relations
        # instead so OrderSerializer stays a single round trip.
        order = (
            Order.objects.select_related("customer", "restaurant", "coupon")
            .prefetch_related("items__food_item")
            .get(pk=order.pk)
        )
        return Response(OrderSerializer(order).data, status=200)