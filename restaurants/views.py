from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import IsCustomer
from .cache import (
    CACHE_TTL_SECONDS,
    restaurant_list_cache_key,
    restaurant_menu_cache_key,
)
from .models import Cart, CartItem, Category, FoodItem, Restaurant
from .permissions import IsOwnerOrReadOnly, IsRestaurantOwnerOfNested
from .serializers import (
    CartItemSerializer,
    CartSerializer,
    CategorySerializer,
    FoodItemSerializer,
    RestaurantSerializer,
)

# in visible_restaurants_for()
def visible_restaurants_for(user):
    if user.is_authenticated and user.role == Role.RESTAURANT_OWNER:
        queryset = Restaurant.objects.filter(Q(is_active=True) | Q(owner=user))
    else:
        queryset = Restaurant.objects.filter(is_active=True)
    return queryset.select_related("owner")


class RestaurantListCreateView(generics.ListCreateAPIView):
    serializer_class = RestaurantSerializer
    permission_classes = [IsOwnerOrReadOnly]

    def get_queryset(self):
        queryset = visible_restaurants_for(self.request.user)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("id")

    def list(self, request, *args, **kwargs):
        # visible_restaurants_for() gives a restaurant_owner an extra row
        # (their own inactive restaurants) that no one else sees. That
        # response is per-user, not the shared public listing, so it must
        # never be served from — or written to — the public cache.
        user = request.user
        is_owner_view = bool(
            user and user.is_authenticated and user.role == Role.RESTAURANT_OWNER
        )
        if is_owner_view:
            return super().list(request, *args, **kwargs)

        cache_key = restaurant_list_cache_key(request.query_params)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, CACHE_TTL_SECONDS)
        return response

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class RestaurantDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = RestaurantSerializer
    permission_classes = [IsOwnerOrReadOnly]

    def get_queryset(self):
        return visible_restaurants_for(self.request.user)


class RestaurantMenuView(generics.ListAPIView):
    serializer_class = FoodItemSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        restaurant = get_object_or_404(
            visible_restaurants_for(self.request.user), pk=self.kwargs["pk"]
        )
        queryset = (
            FoodItem.objects.filter(restaurant=restaurant, is_available=True)
            .select_related("restaurant", "category")
        )
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("id")

    def list(self, request, *args, **kwargs):
        restaurant_id = self.kwargs["pk"]
        # Only cache the genuinely public case. An inactive restaurant's
        # menu is only ever reachable by its own owner — get_object_or_404
        # in get_queryset() above 404s it for everyone else — so it's not
        # shared public data and must always be computed fresh, never read
        # from or written to the cache.
        is_public = Restaurant.objects.filter(
            pk=restaurant_id, is_active=True
        ).exists()

        if not is_public:
            return super().list(request, *args, **kwargs)

        cache_key = restaurant_menu_cache_key(restaurant_id, request.query_params)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, CACHE_TTL_SECONDS)
        return response


class CategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsRestaurantOwnerOfNested]

    def get_queryset(self):
        return Category.objects.filter(
            restaurant_id=self.kwargs["restaurant_id"]
        ).order_by("id")

    def perform_create(self, serializer):
        restaurant = get_object_or_404(Restaurant, pk=self.kwargs["restaurant_id"])
        if restaurant.owner_id != self.request.user.id:
            raise PermissionDenied("You do not own this restaurant.")
        serializer.save(restaurant=restaurant)


class FoodItemCreateView(generics.CreateAPIView):
    serializer_class = FoodItemSerializer
    permission_classes = [IsRestaurantOwnerOfNested]


class FoodItemDetailView(generics.RetrieveUpdateAPIView):
    queryset = FoodItem.objects.select_related("restaurant", "category")
    serializer_class = FoodItemSerializer
    permission_classes = [IsRestaurantOwnerOfNested]
    

def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(customer=user)
    return cart


class CartView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        cart = get_or_create_cart(request.user)
        cart = Cart.objects.select_related("restaurant").prefetch_related(
            "items__food_item"
        ).get(pk=cart.pk)
        return Response(CartSerializer(cart).data)

    def delete(self, request):
        cart = get_or_create_cart(request.user)
        cart.items.all().delete()
        cart.restaurant = None
        cart.save()
        return Response(status=204)


class CartItemCreateView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        food_item_id = request.data.get("food_item")
        quantity = int(request.data.get("quantity", 1))

        food_item = get_object_or_404(FoodItem, pk=food_item_id, is_available=True)

        with transaction.atomic():
            cart, _ = Cart.objects.select_for_update().get_or_create(customer=request.user)

            if cart.restaurant_id is not None and cart.restaurant_id != food_item.restaurant_id:
                return Response(
                    {"detail": "Your cart contains items from another restaurant. Clear it first."},
                    status=400,
                )

            if cart.restaurant_id is None:
                cart.restaurant = food_item.restaurant
                cart.save()

            item, created = CartItem.objects.select_for_update().get_or_create(
                cart=cart, food_item=food_item, defaults={"quantity": quantity}
            )
            if not created:
                item.quantity += quantity
                item.save()

        return Response(CartItemSerializer(item).data, status=201)


class CartItemDetailView(generics.UpdateAPIView, generics.DestroyAPIView):
    serializer_class = CartItemSerializer
    permission_classes = [IsCustomer]

    def get_queryset(self):
        return CartItem.objects.filter(cart__customer=self.request.user)