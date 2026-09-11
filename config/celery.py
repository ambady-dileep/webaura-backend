import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("webaura")

# Load CELERY_* settings from Django's settings.py (the namespace means
# every Celery setting in settings.py must be prefixed with CELERY_).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py files in each installed app (e.g. accounts/tasks.py),
# so future task modules are picked up without manual registration.
app.autodiscover_tasks()