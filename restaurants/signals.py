"""
Cache invalidation for Module 6.1.

Exactly which cache keys get busted by which model event:

* ``Restaurant.save()`` / ``Restaurant.delete()``
    -> wipes ALL ``restaurants:list:*`` keys (name, is_active, and
       description all appear in the public list response, and is_active
       toggling changes which restaurants are even visible there)
    -> wipes ``restaurants:menu:<that restaurant's id>:*`` (an inactive
       restaurant's menu becomes a 404 for the public, and a name change
       isn't shown on the menu endpoint itself, but keeping this in sync
       avoids ever serving a menu page for a restaurant that just went
       inactive out of a stale cache entry)

* ``FoodItem.save()`` / ``FoodItem.delete()``
    -> wipes ``restaurants:menu:<its restaurant's id>:*`` only (a food
       item's price/availability/name never appears in the restaurant
       LIST response, only on that one restaurant's menu, so the list
       cache is left untouched)

We use django-redis's ``cache.delete_pattern()`` rather than tracking every
individual page/search key that might exist, since the set of cached
page/search combinations is unbounded and not worth maintaining a registry
for — deleting the whole prefix on any write is simple, correct, and cheap
compared to a 5-minute TTL anyway.
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import restaurant_list_cache_pattern, restaurant_menu_cache_pattern
from .models import FoodItem, Restaurant


def _bust_restaurant(restaurant_id):
    cache.delete_pattern(restaurant_list_cache_pattern())
    cache.delete_pattern(restaurant_menu_cache_pattern(restaurant_id))


def _bust_menu_only(restaurant_id):
    cache.delete_pattern(restaurant_menu_cache_pattern(restaurant_id))


@receiver(post_save, sender=Restaurant)
def bust_cache_on_restaurant_save(sender, instance, **kwargs):
    _bust_restaurant(instance.id)


@receiver(post_delete, sender=Restaurant)
def bust_cache_on_restaurant_delete(sender, instance, **kwargs):
    _bust_restaurant(instance.id)


@receiver(post_save, sender=FoodItem)
def bust_cache_on_food_item_save(sender, instance, **kwargs):
    _bust_menu_only(instance.restaurant_id)


@receiver(post_delete, sender=FoodItem)
def bust_cache_on_food_item_delete(sender, instance, **kwargs):
    _bust_menu_only(instance.restaurant_id)