from django.contrib import admin

from .models import Coupon


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount_type",
        "value",
        "min_order_amount",
        "max_discount_amount",
        "expiry_date",
        "usage_limit",
        "times_used",
    )
    search_fields = ("code",)