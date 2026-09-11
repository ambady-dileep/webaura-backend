from rest_framework import serializers
from .models import Category, FoodItem, Restaurant
from .models import Cart, CartItem


class RestaurantSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source="owner.username")

    class Meta:
        model = Restaurant
        fields = [
            "id", "owner", "name", "description", "address",
            "is_active", "created_at", "updated_at",
        ]


class CategorySerializer(serializers.ModelSerializer):
    restaurant = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "restaurant", "name"]


class FoodItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodItem
        fields = [
            "id", "restaurant", "category", "name", "description",
            "price", "is_available", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        request = self.context["request"]
        restaurant = attrs.get("restaurant") or getattr(self.instance, "restaurant", None)
        category = attrs.get("category") or getattr(self.instance, "category", None)

        if restaurant is not None and restaurant.owner_id != request.user.id:
            raise serializers.ValidationError(
                {"restaurant": "You do not own this restaurant."}
            )

        if (
            category is not None
            and restaurant is not None
            and category.restaurant_id != restaurant.id
        ):
            raise serializers.ValidationError(
                {"category": "Category does not belong to the specified restaurant."}
            )

        return attrs


class CartItemSerializer(serializers.ModelSerializer):
    food_item_name = serializers.ReadOnlyField(source="food_item.name")
    price = serializers.ReadOnlyField(source="food_item.price")
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id", "food_item", "food_item_name", "price", "quantity", "line_total",
        ]

    def get_line_total(self, obj):
        return obj.food_item.price * obj.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    restaurant = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "restaurant", "items", "subtotal"]

    def get_restaurant(self, obj):
        return obj.restaurant.name if obj.restaurant else None

    def get_subtotal(self, obj):
        return sum(item.food_item.price * item.quantity for item in obj.items.all())