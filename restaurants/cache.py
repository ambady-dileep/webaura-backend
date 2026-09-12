"""
Cache key strategy for the public restaurant list and restaurant menu
endpoints (Module 6.1). Only these two GET endpoints are cached — cart and
orders are per-user and are deliberately never cached here.

Key format
----------
``webaura:restaurants:list:<page>:<search>``
``webaura:restaurants:menu:<restaurant_id>:<page>:<search>``

("webaura:" is CACHES["default"]["KEY_PREFIX"] in settings.py, applied
automatically by django-redis — it is not part of the strings built here.)

Both keys are namespaced by every query parameter that actually changes the
response body (pagination page number and the `?search=` filter), so two
different searches or two different pages of the same restaurant's menu
never collide and never serve each other's cached data. `_normalize` is used
so `?search=Pizza` and `?search=pizza` — which the view treats identically
via `icontains` — also share one cache entry instead of two.

Invalidation (see restaurants/signals.py) does NOT need to enumerate every
page/search combination that might be cached: it uses django-redis's
`delete_pattern` to wipe every key under a prefix in one call, e.g.
``webaura:restaurants:list:*`` or ``webaura:restaurants:menu:<id>:*``.
"""

RESTAURANT_LIST_PREFIX = "restaurants:list"
RESTAURANT_MENU_PREFIX = "restaurants:menu"

CACHE_TTL_SECONDS = 300  # 5 minutes, per the Module 6 spec.


def _normalize(value):
    return (value or "").strip().lower()


def restaurant_list_cache_key(query_params):
    page = _normalize(query_params.get("page")) or "1"
    search = _normalize(query_params.get("search"))
    return f"{RESTAURANT_LIST_PREFIX}:{page}:{search}"


def restaurant_list_cache_pattern():
    return f"{RESTAURANT_LIST_PREFIX}:*"


def restaurant_menu_cache_key(restaurant_id, query_params):
    page = _normalize(query_params.get("page")) or "1"
    search = _normalize(query_params.get("search"))
    return f"{RESTAURANT_MENU_PREFIX}:{restaurant_id}:{page}:{search}"


def restaurant_menu_cache_pattern(restaurant_id):
    return f"{RESTAURANT_MENU_PREFIX}:{restaurant_id}:*"