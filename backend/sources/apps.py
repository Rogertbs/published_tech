from django.apps import AppConfig


class SourcesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sources"
    verbose_name = "Fontes"

    def ready(self):
        from sources.handlers import registrar

        registrar()
