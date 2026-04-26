from django.apps import AppConfig


class ExternalApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.external_api"
    label = "external_api"
    verbose_name = "External API"

    def ready(self):
        # Connect publisher signals so we can fire outbound webhooks on state changes.
        import apps.external_api.signals  # noqa: F401
