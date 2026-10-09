from jobs.handlers import register

from pipeline.motor import executar_pipeline


def _pipeline_handler(tarefa):
    secao = tarefa.parametros.get("secao", "destaques-github")
    execucao = executar_pipeline(tarefa=tarefa, secao=secao)
    return {"execucao": execucao.pk, "estado": execucao.estado}


def registrar():
    register("pipeline")(_pipeline_handler)
