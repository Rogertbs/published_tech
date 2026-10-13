from django.contrib import admin, messages

from jobs import services as jobs
from sources import services
from sources.models import Candidato, Coleta, Fonte, RegistroNormalizado, TipoFonte

SECAO_POR_TIPO = {
    TipoFonte.GITHUB: "destaques-github",
    TipoFonte.HUGGINGFACE: "radar-hf",
}


@admin.register(Fonte)
class FonteAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "habilitada", "credencial_ref", "atualizado_em")
    list_filter = ("tipo", "habilitada")
    search_fields = ("nome",)
    list_per_page = 25
    actions = ["habilitar", "desabilitar", "coletar_agora", "produzir_noticia", "produzir_curadoria"]

    def _enfileirar(self, request, tipo, parametros):
        try:
            tarefa, _ = jobs.executar_agora(tipo, parametros)
        except jobs.MotorPausado:
            self.message_user(request, "Motor pausado: não é possível executar.", level=messages.ERROR)
            return
        self.message_user(
            request, f"{tipo}: tarefa #{tarefa.pk} enfileirada (rascunho pendente de aprovação)."
        )

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

    @admin.action(description="Produzir notícia (fontes RSS)")
    def produzir_noticia(self, request, queryset):
        for fonte in queryset.filter(tipo=TipoFonte.RSS):
            self._enfileirar(request, "noticia", {"fonte_id": fonte.pk})

    @admin.action(description="Produzir curadoria (GitHub/Hugging Face)")
    def produzir_curadoria(self, request, queryset):
        for fonte in queryset.filter(tipo__in=SECAO_POR_TIPO):
            self._enfileirar(
                request, "curadoria", {"secao": SECAO_POR_TIPO[fonte.tipo], "fonte_id": fonte.pk}
            )


@admin.register(Coleta)
class ColetaAdmin(admin.ModelAdmin):
    list_display = ("id", "fonte", "estado", "iniciada_em", "finalizada_em", "total_registros")
    list_filter = ("estado", "fonte__tipo")
    date_hierarchy = "iniciada_em"
    list_select_related = ("fonte",)
    list_per_page = 25
    readonly_fields = ("fonte", "estado", "iniciada_em", "finalizada_em", "total_registros", "erro")


class UsadoFilter(admin.SimpleListFilter):
    title = "uso em conteúdo"
    parameter_name = "uso"

    def lookups(self, request, model_admin):
        return (("usado", "Já usado"), ("novo", "Não usado"))

    def queryset(self, request, queryset):
        if self.value() == "usado":
            return queryset.filter(usado_em__isnull=False)
        if self.value() == "novo":
            return queryset.filter(usado_em__isnull=True)
        return queryset


@admin.register(RegistroNormalizado)
class RegistroNormalizadoAdmin(admin.ModelAdmin):
    list_display = ("chave_externa", "fonte", "coletado_em", "usado_em")
    list_filter = ("fonte", UsadoFilter)
    search_fields = ("chave_externa",)
    date_hierarchy = "coletado_em"
    list_select_related = ("fonte",)
    list_per_page = 25
    readonly_fields = ("fonte", "coleta", "chave_externa", "dados", "coletado_em")


@admin.register(Candidato)
class CandidatoAdmin(admin.ModelAdmin):
    list_display = ("registro", "pontuacao", "selecionado", "criado_em")
    list_filter = ("selecionado",)
    list_select_related = ("registro", "registro__fonte")
    list_per_page = 25
    readonly_fields = ("registro", "pontuacao", "motivo", "criado_em")
