from django.urls import path

from .views import RestaurantDetailView, RestaurantListCreateView

urlpatterns = [
    path("restaurants/", RestaurantListCreateView.as_view(), name="restaurant-list"),
    path("restaurants/<int:pk>/", RestaurantDetailView.as_view(), name="restaurant-detail"),
]