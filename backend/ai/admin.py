from django.contrib import admin

from ai.models import ChamadaIA, PrecoModelo


@admin.register(PrecoModelo)
class PrecoModeloAdmin(admin.ModelAdmin):
    list_display = ("provedor", "modelo", "moeda", "preco_entrada_por_milhao", "preco_saida_por_milhao", "vigente_de")
    list_filter = ("provedor", "moeda")
    search_fields = ("modelo",)


@admin.register(ChamadaIA)
class ChamadaIAAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provedor",
        "modelo",
        "finalidade",
        "status",
        "tokens_entrada",
        "tokens_saida",
        "custo",
        "origem_custo",
        "duracao_ms",
        "iniciada_em",
    )
    list_filter = ("status", "provedor", "finalidade", "origem_custo")
    search_fields = ("modelo", "request_id_externo")
    readonly_fields = (
        "provedor",
        "modelo",
        "finalidade",
        "etapa",
        "tarefa",
        "conteudo_id",
        "correlacao",
        "iniciada_em",
        "finalizada_em",
        "duracao_ms",
        "status",
        "tentativa",
        "request_id_externo",
        "tokens_entrada",
        "tokens_saida",
        "tokens_cache",
        "unidades_imagem",
        "resolucao",
        "moeda",
        "preco_aplicado",
        "custo",
        "origem_custo",
        "erro",
        "criada_em",
    )

    def has_add_permission(self, request):
        return False
