from django.urls import path

from .views import ApplyCouponView

urlpatterns = [
    path("orders/<int:pk>/coupon/", ApplyCouponView.as_view(), name="order-apply-coupon"),
]