from django.apps import AppConfig


class RestaurantsConfig(AppConfig):
    name = "restaurants"

    def ready(self):
        # Registers the post_save/post_delete receivers in signals.py.
        # Imported here (not at module top-level) to avoid the classic
        # Django AppConfig.ready() circular-import trap.
        from . import signals  # noqa: F401