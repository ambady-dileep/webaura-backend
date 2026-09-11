from rest_framework import serializers

from .models import Coupon


class ApplyCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "discount_type",
            "value",
            "min_order_amount",
            "max_discount_amount",
            "expiry_date",
            "usage_limit",
            "times_used",
        ]
        read_only_fields = ["id", "times_used"]