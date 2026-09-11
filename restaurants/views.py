from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import IsCustomer
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
        queryset = FoodItem.objects.filter(restaurant=restaurant, is_available=True)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("id")


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
    queryset = FoodItem.objects.all()
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
