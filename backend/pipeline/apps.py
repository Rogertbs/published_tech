from django.apps import AppConfig


class PipelineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pipeline"
    verbose_name = "Execuções"

    def ready(self):
        from pipeline.handlers import registrar

        registrar()
