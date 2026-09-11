from django.urls import path

from .views import MockPaymentView

urlpatterns = [
    path("payments/<int:order_id>/mock/", MockPaymentView.as_view(), name="mock-payment"),
]