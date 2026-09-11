from django.contrib import admin

from .models import Cart, CartItem, Category, FoodItem, Restaurant

admin.site.register(Restaurant)
admin.site.register(Category)
admin.site.register(FoodItem)
admin.site.register(Cart)
admin.site.register(CartItem)