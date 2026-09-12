# Module 1 — Project Foundation, Authentication & Role-Based Access

**Status:** Complete and tested (25 tests in `accounts/tests.py`).

## Goal

Stand up the project skeleton, Postgres/Redis/Celery wiring, and a JWT auth
system with four roles that every later module enforces against.

## App: `accounts`

### Models

**`User`** (extends `AbstractUser`)
| Field | Type | Notes |
|---|---|---|
| `role` | `CharField` (choices) | `customer`, `restaurant_owner`, `delivery_partner`, `admin` |
| `phone_number` | `CharField`, optional | |

`AUTH_USER_MODEL = "accounts.User"`. A custom `CustomUserManager` overrides
`create_superuser()` to force `role="admin"` regardless of what's passed in
— so `python manage.py createsuperuser` can never produce a mis-rolled
admin account.

### Business rules

- Public registration (`POST /api/auth/register/`) accepts `customer`,
  `restaurant_owner`, and `delivery_partner` only. There is no public path
  to create an `admin` account — those are created via `createsuperuser`
  or Django admin, matching the spec's "admin is not self-registerable"
  rule.
- Auth is fully stateless JWT (access + refresh) via
  `djangorestframework-simplejwt`. No Django session auth is used on the
  API surface.

### Permission classes (`accounts/permissions.py`)

These are the contract every other app builds on:

| Class | Checks |
|---|---|
| `IsCustomer` / `IsRestaurantOwner` / `IsDeliveryPartner` / `IsAdmin` | `request.user.role == <role>` |
| `IsOwnerOfObject` | Generic `has_object_permission` — compares `getattr(obj, view.owner_field)` against `request.user`. `owner_field` defaults to `"owner"` and is overridden per-view (`"customer"` for Cart/Order, `"delivery_partner"` for Delivery, etc.) |

**Pattern used everywhere downstream:** `has_permission` answers "are you
allowed to do this *kind* of thing at all," `has_object_permission` answers
"are you allowed to do this to *this specific* object." This is what makes
a `restaurant_owner` who owns *a* restaurant correctly get `403` (not
`404`) when editing *someone else's* restaurant — DRF only runs
`has_object_permission` after `has_permission` already passed, and a `403`
signals "you're the right kind of user, but not for this object," which is
more informative than a `404` that implies the object doesn't exist.

### API Endpoints

| Method | Endpoint | Access |
|---|---|---|
| POST | `/api/auth/register/` | public |
| POST | `/api/auth/login/` | public — returns JWT access + refresh |
| POST | `/api/auth/refresh/` | public — exchanges refresh token for new access token |

### Infrastructure wired in this module

- `config/celery.py` — `Celery("webaura")` app, `autodiscover_tasks()`,
  loaded via `config/__init__.py` so `@shared_task` is picked up from any
  app's `tasks.py` without manual registration.
- `CACHES["default"]` — `django_redis.cache.RedisCache`, `KEY_PREFIX =
  "webaura"`, `LOCATION` read from `REDIS_CACHE_URL` (defaults to
  `redis://localhost:6379/0`).
- `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` — read from `.env`,
  default to `redis://localhost:6379/1`. Cache and broker are deliberately
  on different logical Redis DBs so `redis-cli -n 0` and `-n 1` never
  collide.

### Acceptance checklist

- [x] Register as customer / restaurant_owner / delivery_partner
- [x] Login returns access + refresh JWT
- [x] A customer JWT gets `403` on any `IsRestaurantOwner`-gated endpoint
- [x] Celery worker starts cleanly and connects to Redis
- [x] `cache.set('x', 1)` / `cache.get('x')` round-trips through Redis