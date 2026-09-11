from django.contrib import admin

from .models import Address, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("food_item_name", "price_at_purchase", "quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "customer", "restaurant", "status", "total_amount", "created_at")
    list_filter = ("status",)
    inlines = [OrderItemInline]


admin.site.register(Address)