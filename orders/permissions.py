from rest_framework.permissions import BasePermission

from accounts.models import Role


class CanUpdateOrderStatus(BasePermission):
    """
    Only a restaurant_owner (for their own restaurant's orders) or an
    admin (for any order) may PATCH an order's status.
    """

    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.role in (Role.RESTAURANT_OWNER, Role.ADMIN)
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == Role.ADMIN:
            return True
        return obj.restaurant.owner_id == request.user.id