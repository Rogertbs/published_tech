from jobs.handlers import register

from sources.services import coletar_todas


@register("coletar")
def coletar_todas_handler(tarefa):
    resultado = coletar_todas()
    return {
        "estado": resultado["estado"],
        "coletas": [c.pk for c in resultado["coletas"]],
    }
