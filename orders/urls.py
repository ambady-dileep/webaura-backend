from django.urls import path

from .views import CheckoutView

urlpatterns = [
    path("orders/checkout/", CheckoutView.as_view(), name="order-checkout"),
]