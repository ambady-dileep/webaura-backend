from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Role, User

# Roles allowed through public self-registration.
# Admin is deliberately excluded — not in this list, so DRF's ChoiceField
# will reject it before a User is ever created.
REGISTERABLE_ROLES = (
    (Role.CUSTOMER, "Customer"),
    (Role.RESTAURANT_OWNER, "Restaurant Owner"),
    (Role.DELIVERY_PARTNER, "Delivery Partner"),
)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=REGISTERABLE_ROLES)

    class Meta:
        model = User
        fields = ["username", "email", "password", "role", "phone_number"]

    def validate_password(self, value):
        # Build an unsaved User instance from the other submitted fields so
        # UserAttributeSimilarityValidator can compare the password against
        # username/email, not just run the other validators blind.
        user = User(
            username=self.initial_data.get("username", ""),
            email=self.initial_data.get("email", ""),
        )
        validate_password(value, user=user)
        return value

    def create(self, validated_data):
        # create_user() hashes the password via set_password() — we
        # never store or handle the raw password ourselves.
        return User.objects.create_user(**validated_data)