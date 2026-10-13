from django.contrib import admin

from pipeline.models import EtapaExecucao, Evidencia, Execucao


class EtapaInline(admin.TabularInline):
    model = EtapaExecucao
    extra = 0
    readonly_fields = ("nome", "saida", "concluida_em")
    can_delete = False


@admin.register(Execucao)
class ExecucaoAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "secao", "estado", "tarefa", "iniciado_em", "finalizado_em")
    list_filter = ("estado", "secao")
    date_hierarchy = "criado_em"
    list_select_related = ("tarefa",)
    list_per_page = 25
    readonly_fields = ("tipo", "secao", "tarefa", "snapshot_config", "iniciado_em", "finalizado_em", "erro", "criado_em")
    inlines = [EtapaInline]


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ("id", "execucao", "versao", "tipo", "url", "verificado")
    list_filter = ("tipo", "verificado")
    list_select_related = ("execucao", "versao", "fonte", "registro")
    list_per_page = 25
    readonly_fields = ("execucao", "versao", "fonte", "registro", "tipo", "url", "trecho", "verificado", "coletado_em", "criado_em")

    def has_add_permission(self, request):
        return False
