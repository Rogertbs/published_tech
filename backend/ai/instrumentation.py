import time
from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone

from ai.models import ChamadaIA, OrigemCusto, PrecoModelo, StatusChamada
from ai.providers import (
    ProvedorErro,
    ProvedorIncerto,
    ProvedorNaoConfigurado,
    ProvedorTimeout,
    obter_provedor,
)

MILHAO = Decimal(1_000_000)
PRECISAO = Decimal("0.000001")


@dataclass
class RespostaIA:
    texto: str
    chamada: ChamadaIA


def _calcular_custo(provedor_nome, modelo, resposta):
    if resposta is not None and resposta.custo_informado is not None:
        return resposta.custo_informado, OrigemCusto.INFORMADO, None

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
        return custo.quantize(PRECISAO), OrigemCusto.ESTIMADO, preco.preco_saida_por_milhao
    return None, OrigemCusto.DESCONHECIDO, None


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
) -> RespostaIA:
    provedor = provedor or obter_provedor()
    modelo = modelo or provedor.modelo_padrao
    inicio = timezone.now()
    t0 = time.monotonic()

    status = StatusChamada.SUCESSO
    erro = ""
    resposta = None
    try:
        resposta = provedor.gerar_texto(prompt, parametros or {}, modelo)
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
    custo, origem_custo, preco_aplicado = _calcular_custo(provedor.nome, modelo, resposta)

    chamada = ChamadaIA.objects.create(
        provedor=provedor.nome,
        modelo=modelo,
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
        request_id_externo=(resposta.request_id if resposta else ""),
        tokens_entrada=(resposta.tokens_entrada if resposta else None),
        tokens_saida=(resposta.tokens_saida if resposta else None),
        tokens_cache=(resposta.tokens_cache if resposta else None),
        moeda=(resposta.moeda if resposta else "USD"),
        preco_aplicado=preco_aplicado,
        custo=custo,
        origem_custo=origem_custo,
        erro=erro,
    )
    return RespostaIA(texto=(resposta.texto if resposta else ""), chamada=chamada)
