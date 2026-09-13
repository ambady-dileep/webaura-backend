from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """
    GET /api/notifications/

    Returns the authenticated user's own notifications, newest first.
    Scoped to request.user - there is no cross-user listing here, so no
    extra object-level permission class is needed beyond IsAuthenticated.
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Notification.objects.filter(user=self.request.user)
            .select_related("order")
            .order_by("-created_at")
        )