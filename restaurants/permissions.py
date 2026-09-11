from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import Role


class IsOwnerOrReadOnly(BasePermission):
    """
    Anyone can read (list/retrieve).
    Only an authenticated restaurant_owner can create.
    Only the restaurant's actual owner can update it.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user.is_authenticated
            and request.user.role == Role.RESTAURANT_OWNER
        )

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.owner_id == request.user.id