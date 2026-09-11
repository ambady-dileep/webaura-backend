from rest_framework import serializers

from .models import Delivery


class DeliverySerializer(serializers.ModelSerializer):
    order_number = serializers.ReadOnlyField(source="order.order_number")
    delivery_partner_username = serializers.ReadOnlyField(
        source="delivery_partner.username", default=None
    )

    class Meta:
        model = Delivery
        fields = [
            "id",
            "order",
            "order_number",
            "delivery_partner",
            "delivery_partner_username",
            "status",
            "assigned_at",
            "picked_up_at",
            "delivered_at",
        ]
        read_only_fields = fields


class AssignDeliverySerializer(serializers.Serializer):
    # Optional — if omitted, the view auto-picks any delivery_partner.
    delivery_partner_id = serializers.IntegerField(required=False)


class DeliveryStatusUpdateSerializer(serializers.Serializer):
    status = serializers.CharField()