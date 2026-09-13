from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    order_number = serializers.ReadOnlyField(source="order.order_number")

    class Meta:
        model = Notification
        fields = ["id", "message", "order", "order_number", "created_at"]
        read_only_fields = fields