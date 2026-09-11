from django.db.models import Q
from rest_framework import generics, permissions

from .models import Restaurant
from .permissions import IsOwnerOrReadOnly
from .serializers import RestaurantSerializer


class RestaurantListCreateView(generics.ListCreateAPIView):
    serializer_class = RestaurantSerializer
    permission_classes = [IsOwnerOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        search = self.request.query_params.get("search")

        if user.is_authenticated and user.role == "restaurant_owner":
            # Owner sees their own restaurants (active or not) plus every
            # other active restaurant — matches "public list + my own,
            # including inactive" without a separate endpoint.
            queryset = Restaurant.objects.filter(
                Q(is_active=True) | Q(owner=user)
            )
        else:
            queryset = Restaurant.objects.filter(is_active=True)

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("id")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class RestaurantDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = RestaurantSerializer
    permission_classes = [IsOwnerOrReadOnly]

    def get_queryset(self):
        # Same visibility rule as the list view, applied per-object:
        # public detail view must 404 an inactive restaurant for
        # non-owners, but the owner can still retrieve/edit their own.
        user = self.request.user
        if user.is_authenticated and user.role == "restaurant_owner":
            return Restaurant.objects.filter(Q(is_active=True) | Q(owner=user))
        return Restaurant.objects.filter(is_active=True)