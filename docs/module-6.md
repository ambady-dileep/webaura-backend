# Module 6 — Redis Caching, Query Optimization, Testing & Documentation

**Status:** Caching and query optimization implemented and tested; full
suite green at 176 tests. This document also tracks the remaining
submission-packaging items.

## 6.1 Redis Caching

Implemented entirely in the `restaurants` app — see `docs/module-2.md` for
the key/invalidation design in detail. Summary:

- **What's cached:** `GET /api/restaurants/` (list) and `GET
  /api/restaurants/{id}/menu/` — both public, both natural caching
  candidates, 5-minute TTL (`CACHE_TTL_SECONDS = 300` in
  `restaurants/cache.py`).
- **What's deliberately never cached:** the restaurant-owner's own list
  view (`RestaurantListCreateView.list()` explicitly bypasses the cache
  when `request.user.role == restaurant_owner`, since that response
  includes the owner's own inactive restaurants and would otherwise leak
  a per-user response into a shared cache key). Cart and order endpoints
  are per-user and were never candidates for this cache.
- **Key format:** `webaura:restaurants:list:<page>:<search>` and
  `webaura:restaurants:menu:<restaurant_id>:<page>:<search>` (`webaura:`
  is `CACHES["default"]["KEY_PREFIX"]`, applied automatically by
  `django-redis`). Search terms are lowercased/stripped before being
  folded into the key so `?search=Pizza` and `?search=pizza` share one
  cache entry.
- **Invalidation:** `restaurants/signals.py` — `post_save`/`post_delete`
  on `Restaurant` bust `restaurants:list:*` and that restaurant's menu
  prefix; on `FoodItem`, only that restaurant's menu prefix (a food item
  never appears on the list response). Uses `cache.delete_pattern()`
  (via `django-redis`, backed by Redis `SCAN`) rather than tracking every
  page/search combination individually — the set of cached combinations
  is unbounded, and wiping the whole prefix on any write is simpler and
  cheap relative to the 5-minute TTL anyway.

**Verify manually:**
```powershell
redis-cli -n 0 keys "webaura:*"
```
Hit `GET /api/restaurants/` twice — a `webaura:restaurants:list:*` key
should appear. Edit that restaurant, re-run the same command — the key
should be gone.

## 6.2 Query Optimization

Applied across all list/detail views added in Modules 2–4:

| View | Optimization |
|---|---|
| `restaurants` list/menu | `select_related("owner")` on Restaurant querysets |
| `Cart` retrieval | `select_related("restaurant")`, `prefetch_related("items__food_item")` |
| `orders` list/detail | `select_related("customer", "restaurant")`, `prefetch_related("items__food_item")` (`get_orders_queryset()` in `orders/views.py`) |
| `coupons` apply | re-fetches with the same `select_related`/`prefetch_related` after mutation, rather than `refresh_from_db()`, to avoid re-triggering lazy queries on serialization |
| `deliveries` list | `select_related("order", "delivery_partner")` |

**Indexes:**
- `Restaurant.name`, `FoodItem.name` — `db_index=True` (search support)
- `Order` — composite indexes on `(restaurant, status)` and `(customer,
  created_at)` via `Order.Meta.indexes`
- `Order.customer` — indexed automatically as a `ForeignKey`

**Pagination:** `DEFAULT_PAGINATION_CLASS =
"rest_framework.pagination.PageNumberPagination"`, `PAGE_SIZE = 10`,
applied project-wide via `REST_FRAMEWORK` settings — every list endpoint
inherits it without per-view configuration.

**To capture a before/after query count** for the README or a PR
description:
```python
from django.test.utils import CaptureQueriesContext
from django.db import connection
from orders.models import Order

with CaptureQueriesContext(connection) as ctx:
    list(Order.objects.select_related("customer", "restaurant")
         .prefetch_related("items__food_item").all())
print(len(ctx.captured_queries))
```

## 6.3 Testing

**176 tests, all passing**, distributed as:

| App | Tests | Covers |
|---|---|---|
| `accounts` | 25 | Registration, JWT login/refresh, all four role permission classes |
| `restaurants` | 41 | Ownership, visibility filtering, single-restaurant cart rule, availability checks, cache hit/miss/invalidation |
| `orders` | 40 | Checkout (empty cart, unavailable items, idempotency, price snapshot), state machine transitions, cross-restaurant access denial |
| `coupons` | 25 | Each rejection reason individually, discount storage survives coupon edits, double-apply protection |
| `payments` | 12 | Idempotent mock payment, `Payment.status` as the sole source of truth |
| `deliveries` | 21 | Assignment rules, forward-only state machine, cross-partner access denial |
| `notifications` | 12 | Retry behavior, auto-cancel (both "still PLACED" and "already ACCEPTED" cases) |

Celery tests use `@override_settings(CELERY_TASK_ALWAYS_EAGER=True,
CELERY_TASK_EAGER_PROPAGATES=True)` so tasks run synchronously in-process
during the test run — this is why triggering a task via `python manage.py
test` doesn't leave a `celery-task-meta-*` key in Redis the way running it
against a live worker does; eager mode skips the broker/result-backend
round trip entirely.

Run everything:
```powershell
python manage.py test
```
Run a single app:
```powershell
python manage.py test notifications
```

## 6.4 Documentation & Submission — status

- [x] `README.md` — present, but **currently describes the project as if
  only Modules 1–2 are done** (see the "Suggestions" note below — this is
  the main documentation debt right now).
- [x] Per-module docs (`docs/module-1.md` … `docs/module-6.md`) — this set.
- [x] `docs/er-diagram.md` — Mermaid ER diagram, up to date with all 6
  modules' models.
- [x] `.env.example` — present, but missing the three Redis/Celery
  variables added during this session (`REDIS_CACHE_URL`,
  `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`) — see suggestions.
- [ ] Postman collection or OpenAPI/Swagger schema (`drf-spectacular`) —
  not yet added.
- [ ] `CHANGELOG.md` or commit history alone as the incremental-commits
  record — confirm the git history reads as meaningful, module-by-module
  commits before final submission, per the assignment's packaging
  checklist.

## Acceptance checklist (whole project, final pass)

- [x] Every list endpoint is paginated
- [x] Restaurant/menu responses are served from cache on repeat hits and go stale correctly after edits
- [x] Full test suite passes (176/176)
- [ ] README lets a stranger clone, configure `.env`, and run the whole stack from scratch — **needs the update described in `docs/module-6.md` §6.4**