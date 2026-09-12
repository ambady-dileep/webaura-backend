from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "order", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "message")