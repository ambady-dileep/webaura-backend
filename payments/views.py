from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCustomer
from orders.models import Order

from .models import Payment
from .serializers import PaymentSerializer


class MockPaymentRequestSerializer(serializers.Serializer):
    # Lets a caller (or a test) simulate either outcome explicitly.
    # Defaults to a successful payment when omitted, since that's the
    # common demo path.
    success = serializers.BooleanField(required=False, default=True)


class MockPaymentView(APIView):
    """
    POST /api/payments/{order_id}/mock/ — customer, own order only.

    This simply flips Payment.status between PENDING/SUCCESS/FAILED to
    simulate a payment gateway callback. Payment.status is the ONLY
    place in the codebase that should ever be checked to decide whether
    an order has been paid for — Order.status is a separate, unrelated
    state machine (see orders.models.Order).
    """

    permission_classes = [IsCustomer]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id, customer=request.user)

        payment, _ = Payment.objects.get_or_create(
            order=order, defaults={"amount": order.total_amount}
        )

        # A payment that already succeeded shouldn't be silently flipped
        # to failed/pending by a stray retry — treat this as idempotent
        # and just hand back the current state.
        if payment.status == Payment.Status.SUCCESS:
            return Response(PaymentSerializer(payment).data, status=200)

        body = MockPaymentRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        payment.amount = order.total_amount
        payment.status = (
            Payment.Status.SUCCESS
            if body.validated_data["success"]
            else Payment.Status.FAILED
        )
        payment.save()

        return Response(PaymentSerializer(payment).data, status=200)