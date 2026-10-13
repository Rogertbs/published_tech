from content.models import Conteudo, Secao
from pipeline.motor import executar_pipeline
from sources import services as sources
from sources.models import EstadoColeta, Fonte, TipoFonte


class SemFonteRSS(Exception):
    pass


def produzir_noticia(*, fonte=None, http_get=None, sleep=None) -> dict:
    fonte = fonte or Fonte.objects.filter(tipo=TipoFonte.RSS, habilitada=True).order_by("id").first()
    if fonte is None:
        raise SemFonteRSS("Nenhuma fonte RSS habilitada.")

    kwargs = {}
    if http_get is not None:
        kwargs["http_get"] = http_get
    if sleep is not None:
        kwargs["sleep"] = sleep

    coleta = sources.coletar(fonte, **kwargs)
    if coleta.estado != EstadoColeta.OK:
        return {"coleta": coleta.estado, "erro": coleta.erro, "conteudo": None}

    sources.selecionar_candidatos(coleta, limite=1)
    execucao = executar_pipeline(secao=Secao.NOTICIAS)
    conteudo = Conteudo.objects.filter(slug=f"{Secao.NOTICIAS}-{execucao.pk}").first()
    versao = conteudo.versao_em_edicao if conteudo else None
    return {
        "fonte": fonte.nome,
        "coleta": coleta.estado,
        "execucao": execucao.pk,
        "estado_execucao": execucao.estado,
        "conteudo": conteudo.slug if conteudo else None,
        "estado_conteudo": conteudo.estado if conteudo else None,
        "versao": versao.pk if versao else None,
        "itens": versao.itens.count() if versao else 0,
        "texto": versao.corpo[:1000] if versao else "",
        "motivo": execucao.motivo,
    }
