from django.contrib import admin, messages

from sources import services
from sources.models import Candidato, Coleta, Fonte, RegistroNormalizado


@admin.register(Fonte)
class FonteAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "habilitada", "credencial_ref", "atualizado_em")
    list_filter = ("tipo", "habilitada")
    search_fields = ("nome",)
    actions = ["habilitar", "desabilitar", "coletar_agora"]

    @admin.action(description="Habilitar fontes")
    def habilitar(self, request, queryset):
        queryset.update(habilitada=True)
        self.message_user(request, "Fonte(s) habilitada(s).")

    @admin.action(description="Desabilitar fontes (interrompe novas coletas)")
    def desabilitar(self, request, queryset):
        queryset.update(habilitada=False)
        self.message_user(request, "Fonte(s) desabilitada(s).")

    @admin.action(description="Coletar agora")
    def coletar_agora(self, request, queryset):
        for fonte in queryset.filter(habilitada=True):
            coleta = services.coletar(fonte)
            self.message_user(request, f"{fonte.nome}: coleta #{coleta.pk} [{coleta.estado}].")
        desabilitadas = queryset.filter(habilitada=False).count()
        if desabilitadas:
            self.message_user(
                request, f"{desabilitadas} fonte(s) desabilitada(s) foram ignoradas.", level=messages.WARNING
            )


@admin.register(Coleta)
class ColetaAdmin(admin.ModelAdmin):
    list_display = ("id", "fonte", "estado", "iniciada_em", "finalizada_em", "total_registros")
    list_filter = ("estado", "fonte__tipo")
    readonly_fields = ("fonte", "estado", "iniciada_em", "finalizada_em", "total_registros", "erro")


@admin.register(RegistroNormalizado)
class RegistroNormalizadoAdmin(admin.ModelAdmin):
    list_display = ("chave_externa", "fonte", "coletado_em")
    list_filter = ("fonte",)
    search_fields = ("chave_externa",)
    readonly_fields = ("fonte", "coleta", "chave_externa", "dados", "coletado_em")


@admin.register(Candidato)
class CandidatoAdmin(admin.ModelAdmin):
    list_display = ("registro", "pontuacao", "selecionado", "criado_em")
    list_filter = ("selecionado",)
    readonly_fields = ("registro", "pontuacao", "motivo", "criado_em")
