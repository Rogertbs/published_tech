from django.contrib.admin import AdminSite
from django.urls import path

from pipeline import producao

GRUPOS = [
    ("Editorial", ["content"]),
    ("Fontes", ["sources"]),
    ("Motor e fila", ["jobs", "pipeline"]),
    ("Custos", ["ai", "finance"]),
    ("Configuração", ["configuracao"]),
    ("Observabilidade", ["auditoria"]),
    ("Autenticação", ["auth"]),
]

MODELOS_TECNICOS = {"chamadaia", "etapaexecucao", "eventotarefa", "registronormalizado"}


class PainelAdmin(AdminSite):
    site_header = "Published Tech"
    site_title = "Published Tech · Painel"
    index_title = "Painel editorial"

    def get_urls(self):
        custom = [
            path("producao/", self.admin_view(producao.index), name="producao_index"),
            path("producao/noticias/", self.admin_view(producao.criar), name="producao_criar"),
            path(
                "producao/tarefas/<int:pk>/status/",
                self.admin_view(producao.tarefa_status),
                name="producao_tarefa_status",
            ),
            path(
                "producao/conteudos/<int:pk>/aprovar/",
                self.admin_view(producao.aprovar),
                name="producao_aprovar",
            ),
            path(
                "producao/conteudos/<int:pk>/publicar/",
                self.admin_view(producao.publicar),
                name="producao_publicar",
            ),
            path(
                "producao/conteudos/<int:pk>/aprovar-publicar/",
                self.admin_view(producao.aprovar_publicar),
                name="producao_aprovar_publicar",
            ),
            path(
                "producao/conteudos/<int:pk>/rejeitar/",
                self.admin_view(producao.rejeitar),
                name="producao_rejeitar",
            ),
            path(
                "producao/conteudos/<int:pk>/retirar/",
                self.admin_view(producao.retirar),
                name="producao_retirar",
            ),
            path(
                "producao/tarefas/<int:pk>/reprocessar/",
                self.admin_view(producao.reprocessar),
                name="producao_reprocessar",
            ),
            path(
                "producao/conteudos/<int:pk>/editar/",
                self.admin_view(producao.editar),
                name="producao_editar",
            ),
            path(
                "producao/conteudos/<int:pk>/regerar/",
                self.admin_view(producao.regerar),
                name="producao_regerar",
            ),
        ]
        return custom + super().get_urls()

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        por_label = {app["app_label"]: app for app in app_list}

        grupos = []
        usados = set()
        for nome, labels in GRUPOS:
            membros = [por_label[label] for label in labels if label in por_label]
            if not membros:
                continue
            usados.update(labels)
            modelos = [
                modelo
                for membro in membros
                for modelo in membro["models"]
                if modelo["object_name"].lower() not in MODELOS_TECNICOS
            ]
            if not modelos:
                continue
            ancora = membros[0]
            grupos.append(
                {
                    "name": nome,
                    "app_label": ancora["app_label"],
                    "app_url": ancora["app_url"],
                    "has_module_perms": any(m["has_module_perms"] for m in membros),
                    "models": modelos,
                }
            )

        for app in app_list:
            if app["app_label"] in usados:
                continue
            modelos = [
                modelo
                for modelo in app["models"]
                if modelo["object_name"].lower() not in MODELOS_TECNICOS
            ]
            if modelos:
                grupos.append(dict(app, models=modelos))

        return grupos
