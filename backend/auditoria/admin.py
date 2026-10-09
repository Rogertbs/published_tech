from django.contrib import admin

from auditoria.models import AuditoriaAdministrativa


@admin.register(AuditoriaAdministrativa)
class AuditoriaAdministrativaAdmin(admin.ModelAdmin):
    list_display = ("id", "acao", "entidade", "entidade_id", "usuario", "criado_em")
    list_filter = ("acao", "entidade")
    readonly_fields = ("usuario", "acao", "entidade", "entidade_id", "antes", "depois", "criado_em")

    def has_add_permission(self, request):
        return False
