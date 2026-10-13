from django.contrib.admin import AdminSite

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
