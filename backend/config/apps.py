from django.contrib.admin.apps import AdminConfig


class PublishedAdminConfig(AdminConfig):
    default_site = "config.admin.PainelAdmin"
