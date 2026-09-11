from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    RESTAURANT_OWNER = "restaurant_owner", "Restaurant Owner"
    DELIVERY_PARTNER = "delivery_partner", "Delivery Partner"
    ADMIN = "admin", "Admin"


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Ensure anyone created via `createsuperuser` is always an admin,
        # regardless of what role (if any) is passed in.
        extra_fields["role"] = Role.ADMIN
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices)
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    objects = CustomUserManager()

    def __str__(self):
        return self.username
    
