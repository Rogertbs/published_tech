from jobs.handlers import register

from sources.services import coletar_todas


def _coletar_todas_handler(tarefa):
    resultado = coletar_todas()
    return {
        "estado": resultado["estado"],
        "coletas": [c.pk for c in resultado["coletas"]],
    }


def registrar():
    register("coletar")(_coletar_todas_handler)
