import time
from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone

from ai.models import ChamadaIA, OrigemCusto, PrecoModelo, StatusChamada
from ai.prompts import envolver_fonte_como_dado
from ai.providers import (
    ProvedorErro,
    ProvedorIncerto,
    ProvedorNaoConfigurado,
    ProvedorTimeout,
    obter_provedor,
)

MILHAO = Decimal(1_000_000)
PRECISAO = Decimal("0.000001")
PADRAO = {"tokens_entrada": None, "tokens_saida": None, "tokens_cache": None, "request_id": ""}


@dataclass
class RespostaIA:
    texto: str
    chamada: ChamadaIA


def _calcular_custo(provedor_nome, modelo, resposta):
    if resposta is not None and resposta.custo_informado is not None:
        return resposta.custo_informado, OrigemCusto.INFORMADO, None, resposta.moeda

    preco = (
        PrecoModelo.objects.filter(provedor=provedor_nome, modelo=modelo)
        .order_by("-vigente_de")
        .first()
    )
    tokens_conhecidos = resposta is not None and None not in (
        resposta.tokens_entrada,
        resposta.tokens_saida,
    )
    if preco and tokens_conhecidos:
        custo = (
            Decimal(resposta.tokens_entrada) * preco.preco_entrada_por_milhao
            + Decimal(resposta.tokens_saida) * preco.preco_saida_por_milhao
        ) / MILHAO
        return custo.quantize(PRECISAO), OrigemCusto.ESTIMADO, preco.preco_saida_por_milhao, preco.moeda
    return None, OrigemCusto.DESCONHECIDO, None, "USD"


def _valores(resposta):
    if resposta is None:
        return PADRAO
    return {
        "tokens_entrada": resposta.tokens_entrada,
        "tokens_saida": resposta.tokens_saida,
        "tokens_cache": resposta.tokens_cache,
        "request_id": resposta.request_id,
    }


def executar_texto(
    prompt: str,
    *,
    finalidade: str,
    etapa: str = "",
    modelo: str | None = None,
    parametros: dict | None = None,
    provedor=None,
    tarefa=None,
    conteudo_id=None,
    correlacao: dict | None = None,
    tentativa: int = 1,
    custo_estimado=None,
    fonte_texto: str | None = None,
) -> RespostaIA:
    provedor = provedor or obter_provedor()
    modelo_solicitado = modelo or provedor.modelo_padrao
    prompt_efetivo = prompt if not fonte_texto else f"{prompt}\n\n{envolver_fonte_como_dado(fonte_texto)}"
    reserva = _reservar_se_pago(provedor, modelo_solicitado, custo_estimado)
    inicio = timezone.now()
    t0 = time.monotonic()

    status = StatusChamada.SUCESSO
    erro = ""
    resposta = None
    try:
        resposta = provedor.gerar_texto(prompt_efetivo, parametros or {}, modelo_solicitado)
    except ProvedorTimeout as exc:
        status, erro = StatusChamada.TIMEOUT, str(exc)
    except ProvedorIncerto as exc:
        status, erro = StatusChamada.INCERTO, str(exc)
    except ProvedorErro as exc:
        status, erro = StatusChamada.ERRO, str(exc)
    except ProvedorNaoConfigurado:
        raise
    except Exception as exc:
        status, erro = StatusChamada.ERRO, str(exc)

    fim = timezone.now()
    duracao_ms = int((time.monotonic() - t0) * 1000)
    modelo_efetivo = resposta.modelo if resposta else modelo_solicitado
    custo, origem_custo, preco_aplicado, moeda = _calcular_custo(
        provedor.nome, modelo_efetivo, resposta
    )
    valores = _valores(resposta)

    chamada = ChamadaIA.objects.create(
        provedor=provedor.nome,
        modelo=modelo_efetivo,
        finalidade=finalidade,
        etapa=etapa,
        tarefa=tarefa,
        conteudo_id=conteudo_id,
        correlacao=correlacao or {},
        iniciada_em=inicio,
        finalizada_em=fim,
        duracao_ms=duracao_ms,
        status=status,
        tentativa=tentativa,
        request_id_externo=valores["request_id"],
        tokens_entrada=valores["tokens_entrada"],
        tokens_saida=valores["tokens_saida"],
        tokens_cache=valores["tokens_cache"],
        moeda=moeda,
        preco_aplicado=preco_aplicado,
        custo=custo,
        origem_custo=origem_custo,
        erro=erro,
    )
    if reserva is not None:
        _conciliar(reserva, chamada)
    return RespostaIA(texto=(resposta.texto if resposta else ""), chamada=chamada)


def _reservar_se_pago(provedor, modelo, custo_estimado):
    if not getattr(provedor, "pago", False):
        return None
    from finance import services as orcamento

    valor = custo_estimado if custo_estimado is not None else orcamento.estimativa_padrao()
    return orcamento.reservar(valor, provedor=provedor.nome, modelo=modelo)


def _conciliar(reserva, chamada):
    from finance import services as orcamento

    orcamento.conciliar(reserva, chamada)
