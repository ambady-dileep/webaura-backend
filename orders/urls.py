from django.urls import path

from .views import CheckoutView, OrderDetailView, OrderListView, OrderStatusUpdateView

urlpatterns = [
    path("orders/checkout/", CheckoutView.as_view(), name="order-checkout"),
    path("orders/", OrderListView.as_view(), name="order-list"),
    path("orders/<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<int:pk>/status/", OrderStatusUpdateView.as_view(), name="order-status-update"),
]