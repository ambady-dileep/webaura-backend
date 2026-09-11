from django.contrib import admin

from .models import Delivery


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("order", "delivery_partner", "status", "assigned_at", "delivered_at")
    list_filter = ("status",)