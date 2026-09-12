# Module 2 — Restaurant, Menu & Cart

**Status:** Complete and tested (41 tests in `restaurants/tests.py`).

## Goal

Restaurant owners manage their restaurant and menu; customers browse and
build a single-restaurant cart.

## App: `restaurants`

### Models

| Model | Key fields | Notes |
|---|---|---|
| `Restaurant` | `owner` (FK→User, `CASCADE`), `name` (indexed), `description`, `address`, `is_active`, timestamps | |
| `Category` | `restaurant` (FK), `name` | |
| `FoodItem` | `restaurant` (FK), `category` (FK), `name` (indexed), `description`, `price` (`Decimal`, never float), `is_available`, timestamps | |
| `Cart` | `customer` (`OneToOneField`→User), `restaurant` (FK, nullable, `SET_NULL`) | Exactly one cart per customer, enforced at the DB level |
| `CartItem` | `cart` (FK), `food_item` (FK), `quantity` | `unique_together (cart, food_item)` — DB-level guarantee that re-adding an item increments quantity instead of duplicating a row |

### Business rules

- **Ownership.** Restaurant/FoodItem CRUD is restricted to the owning
  `restaurant_owner` via `IsOwnerOfObject` (owner_field="owner" on
  Restaurant, and resolved through `food_item.restaurant.owner` on
  FoodItem).
- **Visibility.** Public list/detail/menu querysets filter
  `is_active=True` / `is_available=True` **at the queryset level**, not in
  the serializer — an inactive restaurant never leaves the database in a
  public response, but remains fully visible/editable to its owner.
- **Search.** `?search=` does case-insensitive `icontains` on restaurant
  name (list endpoint) and food item name (menu endpoint).
- **Single-restaurant cart rule.** Before adding a `CartItem`, the view
  checks `cart.restaurant`. If it's set and differs from the new item's
  restaurant, the request is rejected with `400` and a clear message. If
  the cart is empty, `cart.restaurant` is set on first add; clearing the
  cart resets it to `None`.
- **Cart subtotal is never stored.** It's computed on every read as
  `sum(item.quantity * item.food_item.price)`, so it always reflects
  live menu prices — never a stale snapshot (that snapshot only happens
  at checkout, in Module 3).
- **Concurrency.** Adding to a cart is wrapped in `transaction.atomic()`
  with `select_for_update()`, so two near-simultaneous "add to cart"
  requests for the same item can't race into two separate rows before
  either sees the other's write.

### API Endpoints

| Method | Endpoint | Access |
|---|---|---|
| GET | `/api/restaurants/` | public, paginated, `?search=` |
| POST | `/api/restaurants/` | restaurant_owner |
| GET | `/api/restaurants/{id}/` | public |
| PATCH | `/api/restaurants/{id}/` | owner only |
| GET | `/api/restaurants/{id}/menu/` | public, paginated, `?search=` |
| GET / POST | `/api/restaurants/{id}/categories/` | public read / owner-only create |
| POST | `/api/foods/` | owner of the target restaurant only |
| PATCH | `/api/foods/{id}/` | owner only |
| GET | `/api/cart/` | customer (own cart, auto-created on first access) |
| DELETE | `/api/cart/` | customer — clears items, resets `restaurant` to null |
| POST | `/api/cart/items/` | customer — rejects cross-restaurant additions |
| PATCH / DELETE | `/api/cart/items/{id}/` | customer, own cart item only |

### Redis caching (built in this app, wired live in Module 6)

`restaurants/cache.py` and `restaurants/signals.py` already implement the
Module 6.1 caching layer for this app's two public GET endpoints:

- Cache keys are namespaced by every query parameter that changes the
  response body — `restaurants:list:<page>:<search>` and
  `restaurants:menu:<restaurant_id>:<page>:<search>` — so different pages
  or searches never collide or serve each other's cached data. 5-minute
  TTL per the spec.
- `post_save`/`post_delete` signals on `Restaurant` bust both its own menu
  cache and the entire `restaurants:list:*` prefix (name/`is_active`
  changes affect the public list). Signals on `FoodItem` only bust that
  restaurant's menu cache (a food item never appears on the list
  endpoint). See the module docstrings in those two files for the exact
  key-vs-event mapping.
- `cache.delete_pattern()` (from `django-redis`) is used instead of
  tracking individual page/search keys — see `docs/module-6.md` for why.

### Acceptance checklist

- [x] A restaurant owner cannot edit another owner's restaurant/food items (403)
- [x] Deactivating a restaurant removes it from public listing but stays visible to its owner
- [x] Adding items from two different restaurants to the same cart is rejected
- [x] Cart subtotal reflects live menu prices, not a stored value
- [x] Search is case-insensitive and partial-match