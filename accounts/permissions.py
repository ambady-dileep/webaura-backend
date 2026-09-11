from rest_framework.permissions import BasePermission

from .models import Role


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated and request.user.role == Role.CUSTOMER
        )


class IsRestaurantOwner(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.role == Role.RESTAURANT_OWNER
        )


class IsDeliveryPartner(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.role == Role.DELIVERY_PARTNER
        )


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated and request.user.role == Role.ADMIN
        )