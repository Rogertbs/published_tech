import os
import time

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


def obter_conector(fonte: Fonte):
    return CONECTORES.get(fonte.tipo)


def _token(fonte: Fonte) -> str | None:
    if not fonte.credencial_ref:
        return None
    return os.environ.get(fonte.credencial_ref) or None


def coletar(fonte: Fonte, *, http_get=urllib_get, sleep=time.sleep, agora=None) -> Coleta:
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
        except Exception as exc:
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
    return coleta


def coletar_todas(*, http_get=urllib_get, sleep=time.sleep, agora=None) -> dict:
    coletas = []
    for fonte in Fonte.objects.filter(habilitada=True):
        coletas.append(coletar(fonte, http_get=http_get, sleep=sleep, agora=agora))
    houve_falha = any(c.estado in (EstadoColeta.FALHOU, EstadoColeta.FALHOU_PARCIAL) for c in coletas)
    return {"coletas": coletas, "estado": EstadoColeta.FALHOU_PARCIAL if houve_falha else EstadoColeta.OK}


def _pontuacao(dados: dict) -> float:
    estrelas = float(dados.get("estrelas") or 0)
    return estrelas


def _motivo(dados: dict, fonte: Fonte) -> str:
    return (
        f"estrelas={dados.get('estrelas')} "
        f"pushed={dados.get('pushed_em')} "
        f"fonte={fonte.nome}"
    )


def selecionar_candidatos(coleta: Coleta, limite: int | None = None) -> list[Candidato]:
    fonte = coleta.fonte
    limite = limite or int(fonte.parametros.get("selecao", 5))
    registros = list(RegistroNormalizado.objects.filter(fonte=fonte))
    registros.sort(key=lambda r: _pontuacao(r.dados), reverse=True)

    candidatos = []
    for registro in registros[:limite]:
        candidato, _ = Candidato.objects.update_or_create(
            registro=registro,
            defaults={
                "pontuacao": _pontuacao(registro.dados),
                "motivo": _motivo(registro.dados, fonte),
                "selecionado": True,
            },
        )
        candidatos.append(candidato)
    return candidatos
