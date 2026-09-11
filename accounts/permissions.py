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
        
class IsOwnerOfObject(BasePermission):
    """
    Generic object-level ownership check, reusable across every app.

    Set `owner_field` on the view to the attribute name (on the object)
    that points at the User who should be treated as the owner — e.g.
    "owner" for Restaurant, "customer" for Cart/Order, "delivery_partner"
    for Delivery. Defaults to "owner" if the view doesn't specify one.
    """

    owner_field = "owner"

    def has_object_permission(self, request, view, obj):
        owner_field = getattr(view, "owner_field", self.owner_field)
        owner = getattr(obj, owner_field, None)
        return bool(request.user.is_authenticated and owner == request.user)