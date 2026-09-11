from rest_framework import serializers

from .models import Restaurant


class RestaurantSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source="owner.username")

    class Meta:
        model = Restaurant
        fields = [
            "id", "owner", "name", "description", "address",
            "is_active", "created_at", "updated_at",
        ]