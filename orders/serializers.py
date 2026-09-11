from rest_framework import serializers

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = [
            "id", "food_item", "food_item_name",
            "price_at_purchase", "quantity", "line_total",
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    customer = serializers.ReadOnlyField(source="customer.username")
    restaurant = serializers.ReadOnlyField(source="restaurant.name")
    items = OrderItemSerializer(many=True, read_only=True)
    coupon_code = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "customer", "restaurant", "status",
            "delivery_address", "subtotal", "discount_amount",
            "delivery_fee", "tax_amount", "total_amount",
            "coupon", "coupon_code",
            "idempotency_key", "items", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_coupon_code(self, obj):
        return obj.coupon.code if obj.coupon_id else None