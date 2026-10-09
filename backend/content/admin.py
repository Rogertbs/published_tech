from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from content import services
from content.models import Aprovacao, Conteudo, Publicacao, Versao


class VersaoInline(admin.TabularInline):
    model = Versao
    extra = 0
    fields = ("titulo", "criado_em")
    readonly_fields = ("criado_em",)
    show_change_link = True


@admin.register(Conteudo)
class ConteudoAdmin(admin.ModelAdmin):
    list_display = ("slug", "secao", "tipo", "estado_publico", "publicado_em")
    list_filter = ("secao", "tipo")
    search_fields = ("slug",)
    inlines = [VersaoInline]
    actions = ["publicar_selecionados", "retirar_selecionados"]

    @admin.display(boolean=True, description="Publicado")
    def estado_publico(self, obj):
        return obj.esta_publicado

    @admin.action(description="Publicar (versão em edição aprovada)")
    def publicar_selecionados(self, request, queryset):
        for conteudo in queryset:
            versao = services.versao_publicavel(conteudo)
            if versao is None:
                self.message_user(
                    request,
                    f"{conteudo.slug}: aprove a versão em edição antes de publicar.",
                    level=messages.WARNING,
                )
                continue
            services.publicar(conteudo, versao)
            self.message_user(request, f"{conteudo.slug}: publicado.")

    @admin.action(description="Retirar do público")
    def retirar_selecionados(self, request, queryset):
        for conteudo in queryset:
            services.retirar(conteudo)
        self.message_user(request, "Conteúdo(s) retirado(s).")


@admin.register(Versao)
class VersaoAdmin(admin.ModelAdmin):
    list_display = ("__str__", "conteudo", "titulo", "criado_em", "aprovada")
    list_filter = ("conteudo__secao",)
    search_fields = ("titulo", "conteudo__slug")
    actions = ["aprovar_selecionadas"]

    @admin.display(boolean=True, description="Aprovada")
    def aprovada(self, obj):
        return hasattr(obj, "aprovacao")

    @admin.action(description="Aprovar versões selecionadas (origem humana)")
    def aprovar_selecionadas(self, request, queryset):
        for versao in queryset:
            services.aprovar(versao, aprovador=request.user, origem=Aprovacao.Origem.HUMANO)
        self.message_user(request, "Versão(ões) aprovada(s).")


@admin.register(Publicacao)
class PublicacaoAdmin(admin.ModelAdmin):
    list_display = ("conteudo", "versao", "publicado_em", "retirado_em", "ativa")
    list_filter = ("conteudo__secao",)
    readonly_fields = ("conteudo", "versao", "publicado_em", "retirado_em")

    @admin.display(boolean=True, description="Ativa")
    def ativa(self, obj):
        return obj.ativa
