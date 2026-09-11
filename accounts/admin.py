from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("WebAura", {"fields": ("role", "phone_number")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("WebAura", {"fields": ("role", "phone_number")}),
    )
    list_display = UserAdmin.list_display + ("role",)


admin.site.register(User, CustomUserAdmin)