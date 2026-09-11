from django.urls import path

from .views import (
    CategoryListCreateView,
    FoodItemCreateView,
    FoodItemDetailView,
    RestaurantDetailView,
    RestaurantListCreateView,
    RestaurantMenuView,
    CartView,
    CartItemCreateView,
    CartItemDetailView
)

urlpatterns = [
    path("restaurants/", RestaurantListCreateView.as_view(), name="restaurant-list"),
    path("restaurants/<int:pk>/", RestaurantDetailView.as_view(), name="restaurant-detail"),
    path("restaurants/<int:pk>/menu/", RestaurantMenuView.as_view(), name="restaurant-menu"),
    path(
        "restaurants/<int:restaurant_id>/categories/",
        CategoryListCreateView.as_view(),
        name="category-list-create",
    ),
    path("foods/", FoodItemCreateView.as_view(), name="food-create"),
    path("foods/<int:pk>/", FoodItemDetailView.as_view(), name="food-detail"),
    
    path("cart/", CartView.as_view(), name="cart-detail"),
    path("cart/items/", CartItemCreateView.as_view(), name="cart-item-create"),
    path("cart/items/<int:pk>/", CartItemDetailView.as_view(), name="cart-item-detail"),
]