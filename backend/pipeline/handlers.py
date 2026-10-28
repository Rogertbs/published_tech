from jobs.handlers import register

from content.models import Conteudo, Secao
from pipeline.models import Execucao
from pipeline.motor import executar_pipeline
from pipeline.services import (
    produzir_curadoria,
    produzir_noticia,
    resultado_da_execucao,
)
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
    execucao_id = tarefa.parametros.get("execucao_id")
    if execucao_id:
        execucao = Execucao.objects.filter(pk=execucao_id).first()
        if execucao is None:
            raise ValueError("Execução não encontrada para reprocessar.")
        fonte = _fonte_da_tarefa(tarefa)
        execucao = executar_pipeline(
            tarefa=tarefa,
            secao=execucao.secao or Secao.NOTICIAS,
            execucao=execucao,
        )
        alvo = None
        if tarefa.parametros.get("regerar_conteudo_id"):
            alvo = Conteudo.objects.filter(
                pk=tarefa.parametros["regerar_conteudo_id"]
            ).first()
        return resultado_da_execucao(
            execucao, fonte.nome if fonte else "", conteudo=alvo
        )
    return produzir_noticia(fonte=_fonte_da_tarefa(tarefa))


def _curadoria_handler(tarefa):
    secao = tarefa.parametros.get("secao", "destaques-github")
    return produzir_curadoria(secao, fonte=_fonte_da_tarefa(tarefa))


def registrar():
    register("pipeline")(_pipeline_handler)
    register("noticia")(_noticia_handler)
    register("curadoria")(_curadoria_handler)
