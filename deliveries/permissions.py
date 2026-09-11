from rest_framework.permissions import BasePermission

from accounts.models import Role


class CanUpdateDeliveryStatus(BasePermission):
    """
    Only the delivery_partner assigned to this specific Delivery may PATCH
    its status. Admins are read/assign only here — the state machine is
    something only the partner physically doing the delivery should drive.
    """

    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.role == Role.DELIVERY_PARTNER
        )

    def has_object_permission(self, request, view, obj):
        return obj.delivery_partner_id == request.user.id