from django.contrib import admin

from finance.models import ConfiguracaoOrcamento, EventoOrcamento, ReservaOrcamento


@admin.register(ConfiguracaoOrcamento)
class ConfiguracaoOrcamentoAdmin(admin.ModelAdmin):
    list_display = ("__str__", "limite_diario", "limite_mensal", "moeda", "atualizado_em")

    def has_add_permission(self, request):
        return not ConfiguracaoOrcamento.objects.exists()


@admin.register(ReservaOrcamento)
class ReservaOrcamentoAdmin(admin.ModelAdmin):
    list_display = ("id", "provedor", "modelo", "valor_estimado", "estado", "criada_em", "conciliada_em")
    list_filter = ("estado", "provedor")
    readonly_fields = ("provedor", "modelo", "valor_estimado", "moeda", "estado", "chamada", "criada_em", "expira_em", "conciliada_em")

    def has_add_permission(self, request):
        return False


@admin.register(EventoOrcamento)
class EventoOrcamentoAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "limite_atingido", "valor_solicitado", "gasto_dia", "gasto_mes", "criado_em")
    list_filter = ("tipo", "limite_atingido")
    readonly_fields = ("tipo", "limite_atingido", "valor_solicitado", "gasto_dia", "gasto_mes", "detalhe", "criado_em")

    def has_add_permission(self, request):
        return False
