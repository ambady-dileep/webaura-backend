# Module 5 — Celery Background Tasks

**Status:** Complete and tested (12 tests in `notifications/tests.py`, plus
coverage of the checkout-triggered tasks inside `orders/tests.py`).

## Goal

Real asynchronous processing on top of the Celery/Redis wiring from
Module 1 — not just an installed dependency.

## App: `notifications`

### Model — `Notification`

`user` (FK), `order` (FK, nullable — `SET_NULL` so a deleted order doesn't
delete its notification history), `message`, `created_at` (ordered
newest-first).

### Tasks (`notifications/tasks.py`)

**1. `send_order_confirmation_notification(order_id)`**
`@shared_task(bind=True, max_retries=3, default_retry_delay=10)`

- Queued via `.delay(order.id)` from `CheckoutView`, called *after* its
  `transaction.atomic()` block exits successfully (see `orders/views.py`)
  — never from inside it, so a rolled-back checkout never produces a
  phantom notification.
- Re-fetches the order (`select_related("customer", "restaurant")`);
  logs and returns quietly if it no longer exists rather than raising.
- **Retry demo:** `settings.NOTIFICATION_SIMULATED_FAILURE_RATE` (env var,
  default `0.0`) is checked against `random.random()` — set it to `1.0`
  (via `.env` or `override_settings` in a test) to force every attempt to
  fail and watch `self.retry(exc=...)` run up to 3 times in the worker
  log before giving up.
- On success, creates a `Notification` inside its own
  `transaction.atomic()` block.

**2. `expire_unaccepted_order(order_id)`**

- Scheduled via `.apply_async(args=[order.id], countdown=300)` — 5
  minutes — immediately after order creation, no Celery Beat needed since
  it's per-order.
- **Re-fetches the order from the DB with `select_for_update()` inside its
  own `transaction.atomic()`** — never trusts a stale in-memory copy — and
  only cancels it `if order.status == PLACED`. If it's already
  `ACCEPTED`/anything else, it logs and returns without touching the
  order. This re-check is the exact behavior the spec calls out as
  graded.
- Catches `Order.DoesNotExist` (order deleted in the meantime) and
  `InvalidStatusTransition` (e.g. order somehow reached a terminal state
  with no path to `CANCELLED`) without letting either propagate as an
  unhandled task failure.

**3. `daily_restaurant_sales_summary()`** (the "4th task," chosen: daily
sales summary)

- Scheduled nightly via `CELERY_BEAT_SCHEDULE` in `settings.py`
  (`crontab(hour=23, minute=55)`), so this is the one task in the project
  that actually needs Celery Beat running.
- For every active `Restaurant`, aggregates that day's orders
  (`Sum(total_amount)`, `Count(id)`) excluding `CANCELLED`/`REJECTED` from
  the revenue figure, and separately counts cancelled/rejected orders.
- Creates one `Notification` per restaurant owner summarizing the day —
  skipped entirely for restaurants with zero activity (no orders and no
  cancellations) to avoid spamming owners with empty summaries.

### Business rules

- Task failures never corrupt order state — every DB write inside a task
  is wrapped in its own `transaction.atomic()`, independent of whatever
  triggered the task.
- All three tasks import their models lazily (inside the function body,
  not at module scope) to avoid circular imports between `notifications`,
  `orders`, and `restaurants`.

### Acceptance checklist

- [x] Placing an order visibly creates a `Notification` asynchronously (not in the request/response cycle)
- [x] An order accepted within 5 minutes is NOT auto-cancelled
- [x] An order left untouched for 5 minutes IS auto-cancelled
- [x] Forcing the notification task's simulated failure shows it retrying up to 3 times before giving up
- [x] `daily_restaurant_sales_summary` runs and produces a visible `Notification` per active restaurant with activity

### Local verification

```powershell
# Terminal 1
celery -A config worker -l info --pool=solo
# Terminal 2
celery -A config beat -l info
```

Trigger a task manually to inspect worker logs and Redis DB 1:

```python
from notifications.tasks import send_order_confirmation_notification
send_order_confirmation_notification.delay(<some_order_id>)
```

```powershell
redis-cli -n 1 keys "*"
# celery-task-meta-<task-id>, _kombu.binding.celery, etc.
```