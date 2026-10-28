from django.db import transaction

from ai.models import ChamadaIA
from content.models import Conteudo, Secao
from pipeline.models import EstadoExecucao, EtapaExecucao
from pipeline.motor import SECAO_TIPO, executar_pipeline
from sources import services as sources
from sources.models import EstadoColeta, Fonte, TipoFonte

SECOES_CURADORIA = (Secao.DESTAQUES_GITHUB, Secao.RADAR_HF)
ETAPAS_RETENTATIVA = ("redigir", "revisar", "ilustrar", "salvar")


class SemFonte(Exception):
    pass


def _kwargs(http_get, sleep):
    kwargs = {}
    if http_get is not None:
        kwargs["http_get"] = http_get
    if sleep is not None:
        kwargs["sleep"] = sleep
    return kwargs


def resultado_da_execucao(
    execucao, fonte_nome, coleta_estado="ok", coleta_erro="", conteudo=None
):
    if conteudo is None:
        conteudo = Conteudo.objects.filter(slug=f"{execucao.secao}-{execucao.pk}").first()
    versao = conteudo.versao_em_edicao if conteudo else None
    return {
        "fonte": fonte_nome,
        "coleta": coleta_estado,
        "coleta_erro": coleta_erro,
        "execucao": execucao.pk,
        "estado_execucao": execucao.estado,
        "conteudo": conteudo.slug if conteudo else None,
        "estado_conteudo": conteudo.estado if conteudo else None,
        "versao": versao.pk if versao else None,
        "itens": versao.itens.count() if versao else 0,
        "texto": versao.corpo[:1000] if versao else "",
        "motivo": execucao.motivo,
    }


def _resultado(fonte, coleta, execucao):
    return resultado_da_execucao(execucao, fonte.nome, coleta.estado, coleta.erro)


def _resetar_execucao(execucao) -> None:
    EtapaExecucao.objects.filter(
        execucao=execucao, nome__in=ETAPAS_RETENTATIVA
    ).delete()
    execucao.estado = EstadoExecucao.PENDENTE
    execucao.motivo = ""
    execucao.erro = ""
    execucao.finalizado_em = None
    execucao.save(update_fields=["estado", "motivo", "erro", "finalizado_em"])


@transaction.atomic
def preparar_retentativa(execucao) -> None:
    conteudo = Conteudo.objects.filter(slug=f"{execucao.secao}-{execucao.pk}").first()
    if conteudo is not None:
        if conteudo.esta_publicado:
            raise ValueError("Conteúdo já publicado não pode ser reprocessado.")
        ChamadaIA.objects.filter(execucao=execucao, conteudo_id=conteudo.pk).update(
            conteudo_id=None
        )
        conteudo.delete()
    _resetar_execucao(execucao)


@transaction.atomic
def preparar_regeracao(execucao) -> None:
    _resetar_execucao(execucao)


def _executar(fonte, secao, limite, http_get, sleep):
    coleta = sources.coletar(fonte, **_kwargs(http_get, sleep))
    if coleta.estado != EstadoColeta.OK:
        return {"fonte": fonte.nome, "coleta": coleta.estado, "erro": coleta.erro, "conteudo": None}
    sources.selecionar_candidatos(coleta, limite=limite)
    execucao = executar_pipeline(secao=secao, coleta=coleta)
    return _resultado(fonte, coleta, execucao)


def produzir_noticia(*, fonte=None, http_get=None, sleep=None) -> dict:
    fonte = fonte or Fonte.objects.filter(tipo=TipoFonte.RSS, habilitada=True).order_by("id").first()
    if fonte is None:
        raise SemFonte("Nenhuma fonte RSS habilitada.")
    return _executar(fonte, Secao.NOTICIAS, 1, http_get, sleep)


def produzir_curadoria(secao: str, *, fonte=None, http_get=None, sleep=None) -> dict:
    if secao not in SECOES_CURADORIA:
        raise SemFonte(f"Seção de curadoria inválida: '{secao}'.")
    tipo = SECAO_TIPO[secao]
    fonte = fonte or Fonte.objects.filter(tipo=tipo, habilitada=True).order_by("id").first()
    if fonte is None:
        raise SemFonte(f"Nenhuma fonte habilitada para a seção '{secao}'.")
    return _executar(fonte, secao, None, http_get, sleep)
