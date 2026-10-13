from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from content import services
from content.models import Aprovacao, Conteudo, EstadoConteudo, Publicacao, Versao


class VersaoInline(admin.TabularInline):
    model = Versao
    extra = 0
    fields = ("titulo", "criado_em")
    readonly_fields = ("criado_em",)
    show_change_link = True


class FilaRevisaoFilter(admin.SimpleListFilter):
    title = "fila de revisão"
    parameter_name = "fila"

    def lookups(self, request, model_admin):
        return (("revisao", "Aguardando revisão"), ("rascunho", "Rascunhos"))

    def queryset(self, request, queryset):
        if self.value() == "revisao":
            return queryset.filter(estado=EstadoConteudo.AGUARDANDO_REVISAO)
        if self.value() == "rascunho":
            return queryset.filter(estado=EstadoConteudo.RASCUNHO)
        return queryset


@admin.register(Conteudo)
class ConteudoAdmin(admin.ModelAdmin):
    list_display = ("slug", "secao", "tipo", "estado", "estado_publico", "publicado_em")
    list_filter = ("secao", "tipo", "estado", FilaRevisaoFilter)
    search_fields = ("slug", "versoes__titulo")
    date_hierarchy = "criado_em"
    list_select_related = ("versao_publicada", "versao_em_edicao")
    list_per_page = 25
    inlines = [VersaoInline]
    actions = ["aprovar_e_publicar", "publicar_selecionados", "retirar_selecionados"]

    @admin.display(boolean=True, description="Publicado")
    def estado_publico(self, obj):
        return obj.esta_publicado

    def get_urls(self):
        custom = [
            path(
                "<path:object_id>/aprovar-publicar/",
                self.admin_site.admin_view(self.acao_aprovar_publicar),
                name="content_conteudo_aprovar_publicar",
            ),
            path(
                "<path:object_id>/publicar/",
                self.admin_site.admin_view(self.acao_publicar),
                name="content_conteudo_publicar",
            ),
            path(
                "<path:object_id>/retirar/",
                self.admin_site.admin_view(self.acao_retirar),
                name="content_conteudo_retirar",
            ),
        ]
        return custom + super().get_urls()

    def _voltar(self, object_id):
        return HttpResponseRedirect(
            reverse("admin:content_conteudo_change", args=[object_id])
        )

    def _objeto_post(self, request, object_id):
        conteudo = self.get_object(request, object_id)
        if conteudo is None or request.method != "POST":
            return None
        return conteudo

    def _aprovar_publicar(self, conteudo, usuario):
        versao = conteudo.versao_em_edicao
        if versao is None:
            return None
        services.aprovar(versao, aprovador=usuario, origem=Aprovacao.Origem.HUMANO)
        services.publicar(conteudo, versao)
        return versao

    def acao_aprovar_publicar(self, request, object_id):
        conteudo = self._objeto_post(request, object_id)
        if conteudo is None:
            return self._voltar(object_id)
        if self._aprovar_publicar(conteudo, request.user) is None:
            self.message_user(
                request, "Sem versão em edição para aprovar.", level=messages.WARNING
            )
        else:
            self.message_user(request, f"{conteudo.slug}: aprovado e publicado.")
        return self._voltar(object_id)

    def acao_publicar(self, request, object_id):
        conteudo = self._objeto_post(request, object_id)
        if conteudo is None:
            return self._voltar(object_id)
        versao = services.versao_publicavel(conteudo)
        if versao is None:
            self.message_user(
                request,
                "Aprove a versão em edição antes de publicar.",
                level=messages.WARNING,
            )
            return self._voltar(object_id)
        services.publicar(conteudo, versao)
        self.message_user(request, f"{conteudo.slug}: publicado.")
        return self._voltar(object_id)

    def acao_retirar(self, request, object_id):
        conteudo = self._objeto_post(request, object_id)
        if conteudo is None:
            return self._voltar(object_id)
        services.retirar(conteudo)
        self.message_user(request, f"{conteudo.slug}: retirado do público.")
        return self._voltar(object_id)

    @admin.action(description="Aprovar e publicar (versão em edição)")
    def aprovar_e_publicar(self, request, queryset):
        for conteudo in queryset:
            if self._aprovar_publicar(conteudo, request.user) is None:
                self.message_user(
                    request, f"{conteudo.slug}: sem versão em edição.", level=messages.WARNING
                )
                continue
            self.message_user(request, f"{conteudo.slug}: aprovado e publicado.")

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
    date_hierarchy = "criado_em"
    list_select_related = ("conteudo",)
    list_per_page = 25
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
    date_hierarchy = "publicado_em"
    list_select_related = ("conteudo", "versao")
    readonly_fields = ("conteudo", "versao", "publicado_em", "retirado_em")

    @admin.display(boolean=True, description="Ativa")
    def ativa(self, obj):
        return obj.ativa
