import os
import time
from datetime import datetime

from django.utils import timezone

from sources.connectors.base import ConectorError, RateLimitPersistente
from sources.connectors.github import GitHubConector, urllib_get
from sources.models import (
    Candidato,
    Coleta,
    EstadoColeta,
    Fonte,
    RegistroNormalizado,
    TipoFonte,
)

CONECTORES = {
    TipoFonte.GITHUB: GitHubConector(),
}


class FonteDesabilitada(Exception):
    pass


def obter_conector(fonte: Fonte):
    return CONECTORES.get(fonte.tipo)


def _token(fonte: Fonte) -> str | None:
    if not fonte.credencial_ref:
        return None
    return os.environ.get(fonte.credencial_ref) or None


def coletar(fonte: Fonte, *, http_get=urllib_get, sleep=time.sleep, agora=None) -> Coleta:
    if not fonte.habilitada:
        raise FonteDesabilitada(f"A fonte '{fonte.nome}' está desabilitada.")

    agora = agora or timezone.now()
    coleta = Coleta.objects.create(fonte=fonte, iniciada_em=agora, estado=EstadoColeta.EM_ANDAMENTO)

    conector = obter_conector(fonte)
    if conector is None:
        coleta.estado = EstadoColeta.FALHOU
        coleta.erro = f"Sem conector para o tipo '{fonte.tipo}'."
    else:
        try:
            registros = conector.listar(
                fonte.parametros, _token(fonte), http_get=http_get, sleep=sleep
            )
        except RateLimitPersistente as exc:
            coleta.estado = EstadoColeta.FALHOU_PARCIAL
            coleta.erro = str(exc)
        except ConectorError as exc:
            coleta.estado = EstadoColeta.FALHOU
            coleta.erro = str(exc)
        else:
            for registro in registros:
                RegistroNormalizado.objects.update_or_create(
                    fonte=fonte,
                    chave_externa=registro["chave_externa"],
                    defaults={"dados": registro["dados"], "coleta": coleta, "coletado_em": agora},
                )
            coleta.total_registros = len(registros)
            coleta.estado = EstadoColeta.OK

    coleta.finalizada_em = timezone.now()
    coleta.save()

    if coleta.estado == EstadoColeta.OK:
        selecionar_candidatos(coleta)
    return coleta


def coletar_todas(*, http_get=urllib_get, sleep=time.sleep, agora=None) -> dict:
    coletas = []
    for fonte in Fonte.objects.filter(habilitada=True):
        try:
            coletas.append(coletar(fonte, http_get=http_get, sleep=sleep, agora=agora))
        except FonteDesabilitada:
            continue

    falhas = [c for c in coletas if c.estado in (EstadoColeta.FALHOU, EstadoColeta.FALHOU_PARCIAL)]
    if not coletas:
        estado = EstadoColeta.OK
    elif len(falhas) == len(coletas):
        estado = EstadoColeta.FALHOU
    elif falhas:
        estado = EstadoColeta.FALHOU_PARCIAL
    else:
        estado = EstadoColeta.OK
    return {"coletas": coletas, "estado": estado}


def _dias_desde(valor) -> int | None:
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (timezone.now() - momento).days


def _pontuacao(dados: dict, fonte: Fonte) -> float:
    estrelas = float(dados.get("estrelas") or 0)
    forks = float(dados.get("forks") or 0)
    janela = int(fonte.parametros.get("janela_dias", 7))
    dias = _dias_desde(dados.get("pushed_em"))
    bonus_recencia = 1000.0 if dias is not None and dias <= janela else 0.0
    return estrelas + 2 * forks + bonus_recencia


def _motivo(dados: dict, fonte: Fonte) -> str:
    janela = int(fonte.parametros.get("janela_dias", 7))
    return (
        f"curadoria própria (não é o ranking oficial do GitHub): "
        f"estrelas={dados.get('estrelas')}, forks={dados.get('forks')}, "
        f"atualizado_em={dados.get('pushed_em')}, licença={dados.get('licenca')}, "
        f"janela={janela}d"
    )


def selecionar_candidatos(coleta: Coleta, limite: int | None = None) -> list[Candidato]:
    fonte = coleta.fonte
    limite = limite or int(fonte.parametros.get("selecao", 5))
    registros = list(RegistroNormalizado.objects.filter(coleta=coleta))
    registros.sort(key=lambda r: _pontuacao(r.dados, fonte), reverse=True)

    candidatos = []
    for registro in registros[:limite]:
        candidato, _ = Candidato.objects.update_or_create(
            registro=registro,
            defaults={
                "pontuacao": _pontuacao(registro.dados, fonte),
                "motivo": _motivo(registro.dados, fonte),
                "selecionado": True,
            },
        )
        candidatos.append(candidato)
    return candidatos
