from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role, User
from accounts.permissions import IsAdmin
from orders.models import Order, OrderStatus

from .models import Delivery, DeliveryStatus, InvalidDeliveryTransition
from .permissions import CanUpdateDeliveryStatus
from .serializers import (
    AssignDeliverySerializer,
    DeliverySerializer,
    DeliveryStatusUpdateSerializer,
)


def _pick_available_delivery_partner():
    """
    "Simple assign to any available delivery_partner" logic per the spec:
    a delivery_partner counts as available if they have no delivery
    currently in a non-terminal state (i.e. nothing short of DELIVERED).
    """
    busy_partner_ids = Delivery.objects.exclude(
        status=DeliveryStatus.DELIVERED
    ).exclude(delivery_partner__isnull=True).values_list("delivery_partner_id", flat=True)
    return (
        User.objects.filter(role=Role.DELIVERY_PARTNER)
        .exclude(id__in=list(busy_partner_ids))
        .first()
    )


class AssignDeliveryView(APIView):
    """
    POST /api/orders/{id}/assign-delivery/ — admin only.

    Creates the Delivery for an order. Per the spec, only an ACCEPTED
    order can get a Delivery created against it, and this is the "admin
    (or simple auto-assign) creates the assignment" step — the delivery
    partner themselves never creates their own assignment.
    """

    permission_classes = [IsAdmin]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        if order.status != OrderStatus.ACCEPTED:
            return Response(
                {"detail": "Only an ACCEPTED order can be assigned a delivery."},
                status=400,
            )

        if Delivery.objects.filter(order=order).exists():
            return Response(
                {"detail": "This order already has a delivery assigned."},
                status=400,
            )

        body = AssignDeliverySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        partner_id = body.validated_data.get("delivery_partner_id")

        if partner_id:
            partner = get_object_or_404(
                User, pk=partner_id, role=Role.DELIVERY_PARTNER
            )
        else:
            partner = _pick_available_delivery_partner()
            if partner is None:
                return Response(
                    {"detail": "No available delivery partners right now."},
                    status=400,
                )

        with transaction.atomic():
            delivery = Delivery.objects.create(
                order=order,
                delivery_partner=partner,
                status=DeliveryStatus.ASSIGNED,
                assigned_at=timezone.now(),
            )

        return Response(DeliverySerializer(delivery).data, status=201)


class DeliveryListView(generics.ListAPIView):
    """
    GET /api/deliveries/ — delivery_partner sees only their own
    assignments; admin sees all.
    """

    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        base = Delivery.objects.select_related(
            "order", "delivery_partner"
        ).order_by("-id")
        if user.role == Role.DELIVERY_PARTNER:
            return base.filter(delivery_partner=user)
        if user.role == Role.ADMIN:
            return base
        return base.none()


class DeliveryStatusUpdateView(APIView):
    """
    PATCH /api/deliveries/{id}/status/ — delivery_partner, own assignment
    only. Status can only move forward through the defined sequence; any
    other transition (skip or backward) is rejected with 400.
    """

    permission_classes = [CanUpdateDeliveryStatus]

    def patch(self, request, pk):
        delivery = get_object_or_404(
            Delivery.objects.select_related("order", "delivery_partner"), pk=pk
        )
        self.check_object_permissions(request, delivery)

        body = DeliveryStatusUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        new_status = body.validated_data["status"]

        if new_status not in DeliveryStatus.values:
            return Response(
                {"detail": f"'{new_status}' is not a valid delivery status."},
                status=400,
            )

        try:
            with transaction.atomic():
                delivery.transition_to(new_status)
                delivery.save()
        except InvalidDeliveryTransition as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(DeliverySerializer(delivery).data, status=200)