from jobs.handlers import register

from pipeline.motor import executar_pipeline
from pipeline.services import produzir_curadoria, produzir_noticia
from sources.models import Fonte


def _pipeline_handler(tarefa):
    secao = tarefa.parametros.get("secao", "destaques-github")
    execucao = executar_pipeline(tarefa=tarefa, secao=secao)
    return {"execucao": execucao.pk, "estado": execucao.estado}


def _fonte_da_tarefa(tarefa):
    if tarefa.parametros.get("fonte_id"):
        return Fonte.objects.filter(pk=tarefa.parametros["fonte_id"]).first()
    return None


def _noticia_handler(tarefa):
    return produzir_noticia(fonte=_fonte_da_tarefa(tarefa))


def _curadoria_handler(tarefa):
    secao = tarefa.parametros.get("secao", "destaques-github")
    return produzir_curadoria(secao, fonte=_fonte_da_tarefa(tarefa))


def registrar():
    register("pipeline")(_pipeline_handler)
    register("noticia")(_noticia_handler)
    register("curadoria")(_curadoria_handler)
