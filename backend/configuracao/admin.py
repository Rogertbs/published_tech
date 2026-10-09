from django.contrib import admin, messages

from configuracao.models import Configuracao, SnapshotConfiguracao, VersaoConfiguracao
from configuracao.services import ativar_versao


class VersaoInline(admin.TabularInline):
    model = VersaoConfiguracao
    extra = 0
    fields = ("numero", "ativa", "campos", "criada_em")
    readonly_fields = ("numero", "criada_em")


@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ("chave", "escopo", "secao", "agente", "atualizado_em")
    list_filter = ("escopo",)
    search_fields = ("chave",)
    inlines = [VersaoInline]


@admin.register(VersaoConfiguracao)
class VersaoConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ("configuracao", "numero", "ativa", "criada_em")
    list_filter = ("ativa", "configuracao__escopo")
    actions = ["ativar"]

    @admin.action(description="Ativar versões selecionadas")
    def ativar(self, request, queryset):
        for versao in queryset:
            ativar_versao(versao)
        self.message_user(request, "Versão(ões) ativada(s).")


@admin.register(SnapshotConfiguracao)
class SnapshotConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ("id", "tarefa", "criado_em")
    readonly_fields = ("tarefa", "campos", "versoes", "criado_em")

    def has_add_permission(self, request):
        return False
