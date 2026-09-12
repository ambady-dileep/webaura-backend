# Module 4 — Coupons, Mock Payments & Delivery

**Status:** Complete and tested (25 tests in `coupons/tests.py`, 12 in
`payments/tests.py`, 21 in `deliveries/tests.py`).

## Goal

Layer discount logic, a mock payment gate, and delivery
assignment/tracking onto the order flow from Module 3.

## App: `coupons`

### Model — `Coupon`

`code` (unique), `discount_type` (`flat`/`percentage`), `value`,
`min_order_amount`, `max_discount_amount` (nullable, caps percentage
discounts), `expiry_date`, `usage_limit`, `times_used`.

### Business rules

- **`validate_coupon(coupon, subtotal)`** runs checks in the spec's exact
  order and raises a `CouponError` carrying a machine-readable `code` —
  `expired` → `usage_limit_reached` → `below_minimum_order_amount` — so
  the API returns a distinct reason per failure instead of one generic
  "invalid coupon" message.
- **`Coupon.compute_discount(subtotal)`** computes the actual discount
  (flat value, or percentage capped by `max_discount_amount`, and never
  more than the subtotal itself) — called only after validation passes.
- **`ApplyCouponView`** (`POST /api/orders/{id}/coupon/`):
  - Only works on an order that is still `PLACED` and has no
    `Payment.status == SUCCESS` record — **payment state is checked via
    `Payment`, never `Order.status`**, per the Module 4 spec's
    single-source-of-truth rule.
  - Rejects outright if the order already has a coupon
    (`coupon_already_applied`) — this doubles as the guard against
    double-incrementing `Coupon.times_used` on a retried request.
  - The discount and `total_amount` are computed and **stored directly on
    the `Order`** (not just a coupon reference), so editing or deleting
    the `Coupon` later never changes an already-applied order's total.
  - Wrapped in `transaction.atomic()` with `select_for_update()` on the
    order row, re-checking the "already applied" guard *inside* the lock
    (the outer check is just a fast, unlocked pre-check for a friendlier
    error on the common path) before incrementing
    `Coupon.times_used` via `F("times_used") + 1` (atomic increment, no
    read-modify-write race).

## App: `payments`

### Model — `Payment`

`order` (`OneToOne`), `status` (`pending`/`success`/`failed`), `amount`,
timestamps.

### Business rules

- **`Payment.status` is the only place in the codebase that decides
  whether an order has been paid for.** `Order.status` is a separate,
  unrelated state machine — nothing checks `order.status` to infer
  payment.
- `MockPaymentView` (`POST /api/payments/{order_id}/mock/`) simulates a
  gateway callback via a `success: bool` body flag (defaults to `True`).
  It's idempotent: a payment that already succeeded is returned as-is,
  never silently flipped back to `pending`/`failed` by a stray retry.

## App: `deliveries`

### Model — `Delivery`

`order` (`OneToOne`), `delivery_partner` (FK, nullable until assigned),
`status` (`unassigned`/`assigned`/`picked_up`/`out_for_delivery`/`delivered`),
`assigned_at`/`picked_up_at`/`delivered_at` timestamps set automatically
by `transition_to()` as each stage happens.

### Business rules

- **Only an `ACCEPTED` order can get a `Delivery`.** `AssignDeliveryView`
  (`POST /api/orders/{id}/assign-delivery/`, admin only) rejects
  otherwise, and rejects assigning a second delivery to an order that
  already has one.
- **Assignment logic** — `_pick_available_delivery_partner()` treats a
  delivery_partner as "available" if they have no delivery currently in a
  non-terminal state (anything short of `DELIVERED`). An explicit
  `delivery_partner_id` in the request body overrides auto-pick.
- **Forward-only state machine**, same explicit-map pattern as
  `Order.ALLOWED_TRANSITIONS`: `UNASSIGNED → ASSIGNED → PICKED_UP →
  OUT_FOR_DELIVERY → DELIVERED`, each a one-way door. Skipping or
  reversing a stage raises `InvalidDeliveryTransition` → `400`.
- **Ownership.** Only the assigned `delivery_partner` can `PATCH` their
  own `Delivery`'s status (`CanUpdateDeliveryStatus`); admins can list all
  deliveries but do not drive the state machine themselves.

### API Endpoints

| Method | Endpoint | Access |
|---|---|---|
| POST | `/api/orders/{id}/coupon/` | customer, own order, not yet paid |
| POST | `/api/payments/{order_id}/mock/` | customer, own order |
| POST | `/api/orders/{id}/assign-delivery/` | admin |
| GET | `/api/deliveries/` | delivery_partner (own) / admin (all) |
| PATCH | `/api/deliveries/{id}/status/` | delivery_partner, own assignment only |

### Acceptance checklist

- [x] Expired, exhausted, and below-minimum coupons each get a distinguishable error
- [x] `Order.discount_amount` survives even if the coupon is later edited/deleted
- [x] A `Payment.status = pending` order is never treated as paid anywhere
- [x] A delivery partner PATCHing another partner's delivery gets `403`
- [x] Delivery status can't skip states or move backward