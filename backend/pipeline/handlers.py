from jobs.handlers import register

from pipeline.motor import executar_pipeline
from pipeline.services import produzir_noticia
from sources.models import Fonte


def _pipeline_handler(tarefa):
    secao = tarefa.parametros.get("secao", "destaques-github")
    execucao = executar_pipeline(tarefa=tarefa, secao=secao)
    return {"execucao": execucao.pk, "estado": execucao.estado}


def _noticia_handler(tarefa):
    fonte = None
    if tarefa.parametros.get("fonte_id"):
        fonte = Fonte.objects.filter(pk=tarefa.parametros["fonte_id"]).first()
    return produzir_noticia(fonte=fonte)


def registrar():
    register("pipeline")(_pipeline_handler)
    register("noticia")(_noticia_handler)
