# WebAura Backend — Command Reference

Quick reference for every command used to set up, run, test, and debug this
project. Grouped by task. All commands assume PowerShell on Windows and the
venv already created (`python -m venv venv`), run from the project root
(`D:\Brototype\webaura-backend`).

---

## 1. Environment setup

```powershell
# Activate the virtual environment
venv\Scripts\Activate.ps1

# If PowerShell blocks script execution the first time:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
venv\Scripts\Activate.ps1

# Install/sync dependencies from requirements.txt
pip install -r requirements.txt

# Reinstall after changing a pinned version in requirements.txt
pip install -r requirements.txt --upgrade
```

---

## 2. Django — running the server

```powershell
# Check for missing migrations without creating them
python manage.py makemigrations --check --dry-run

# Create new migrations from model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Run Django's system checks (settings, models, etc.)
python manage.py check

# Start the dev server (http://127.0.0.1:8000/)
python manage.py runserver

# Create an admin account (always role=admin, enforced by CustomUserManager)
python manage.py createsuperuser

# Open the interactive Django shell
python manage.py shell
```

---

## 3. Redis & Celery

```powershell
# Start Redis (if installed locally, not as a service)
redis-server

# Start the Celery worker (--pool=solo avoids Windows multiprocessing issues)
celery -A config worker -l info --pool=solo

# Start Celery Beat (only needed for daily_restaurant_sales_summary)
celery -A config beat -l info
```

Run the worker and beat in **separate terminals**, alongside the Django dev
server — all three need to be running at once for the full stack (order
confirmation, auto-expiry, and the nightly summary) to actually work
end-to-end.

---

## 4. Testing

```powershell
# Run the full test suite (176 tests across all 7 apps)
python manage.py test

# Run a single app's tests
python manage.py test accounts
python manage.py test restaurants
python manage.py test orders
python manage.py test coupons
python manage.py test payments
python manage.py test deliveries
python manage.py test notifications

# Run a single test case or method (dotted path)
python manage.py test orders.tests.CheckoutTests
python manage.py test orders.tests.CheckoutTests.test_idempotent_checkout
```

---

## 5. Manual verification (Django shell)

```powershell
python manage.py shell
```

```python
# Cache round-trip check
from django.core.cache import cache
cache.set('x', 1)
cache.get('x')                              # -> 1
cache.delete_pattern('restaurants:list:*')  # -> 0 or count of keys cleared

# Manually trigger a Celery task (worker must be running in another terminal)
from notifications.tasks import send_order_confirmation_notification
send_order_confirmation_notification.delay(1)   # replace 1 with a real order id

# Force the simulated notification-retry failure path
from django.test import override_settings
with override_settings(NOTIFICATION_SIMULATED_FAILURE_RATE=1.0):
    from notifications.tasks import send_order_confirmation_notification
    send_order_confirmation_notification.delay(1)

# Query-count / N+1 spot check
from django.test.utils import CaptureQueriesContext
from django.db import connection
from orders.models import Order

with CaptureQueriesContext(connection) as ctx:
    list(Order.objects.select_related("customer", "restaurant")
         .prefetch_related("items__food_item").all())
print(len(ctx.captured_queries))
```

---

## 6. Redis CLI checks

```powershell
# List cache keys (DB 0)
redis-cli -n 0 keys "*"
redis-cli -n 0 keys "webaura:*"

# List Celery broker/result keys (DB 1)
redis-cli -n 1 keys "*"

# Check the Redis server version (relevant if you ever change the redis-py pin)
redis-cli INFO server | Select-String "redis_version"

# Watch every command hitting Redis live (useful for confirming cache hits)
redis-cli MONITOR
```

---

## 7. Git

```powershell
# Stage everything
git add .

# Commit with a multi-line message from a file (avoids PowerShell quoting issues)
@"
<type>: <short summary>

<body>
"@ | Set-Content -Path commit_msg.txt -Encoding utf8
git commit -F commit_msg.txt
Remove-Item commit_msg.txt

# Commit with a single-line message
git commit -m "type: short summary"

# Check commit history reads as clean, incremental commits before submission
git log --oneline

# Confirm nothing under venv/ ever got tracked
git ls-files | Select-String "venv/"

# Untrack a file that was committed by mistake (keeps it on disk, stops tracking it)
git rm --cached <path>
```

---

## 8. One-time / setup-only commands

```sql
-- PostgreSQL: create the project database and user
CREATE DATABASE webaura;
CREATE USER webaura_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE webaura TO webaura_user;
ALTER USER webaura_user CREATEDB;  -- needed so Django's test runner can create/drop the test DB
```

```powershell
# Copy the env template and fill in real values
cp .env.example .env
```

---

## Typical local dev session (in order)

```powershell
venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver          # Terminal 1
celery -A config worker -l info --pool=solo   # Terminal 2
celery -A config beat -l info                 # Terminal 3 (only if testing the daily summary)
python manage.py test               # Terminal 4, as needed
```