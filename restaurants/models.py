from django.conf import settings
from django.db import models


class Restaurant(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="restaurants",
    )
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    address = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"


class FoodItem(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="food_items"
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="food_items"
    )
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Cart(models.Model):
    customer = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart({self.customer.username})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("cart", "food_item")

    def __str__(self):
        return f"{self.quantity} x {self.food_item.name}"