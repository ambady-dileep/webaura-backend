from django.urls import path

from .views import AssignDeliveryView, DeliveryListView, DeliveryStatusUpdateView

urlpatterns = [
    path("deliveries/", DeliveryListView.as_view(), name="delivery-list"),
    path(
        "deliveries/<int:pk>/status/",
        DeliveryStatusUpdateView.as_view(),
        name="delivery-status-update",
    ),
    path(
        "orders/<int:order_id>/assign-delivery/",
        AssignDeliveryView.as_view(),
        name="assign-delivery",
    ),
]