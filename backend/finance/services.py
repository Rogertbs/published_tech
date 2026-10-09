import csv
import io
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from ai.models import ChamadaIA
from finance.models import ConfiguracaoOrcamento, EstadoReserva, EventoOrcamento, ReservaOrcamento

ZERO = Decimal("0")


class OrcamentoExcedido(Exception):
    def __init__(self, limite_atingido, valor_solicitado, gasto_dia, gasto_mes):
        super().__init__(f"Orçamento {limite_atingido} excedido.")
        self.limite_atingido = limite_atingido
        self.valor_solicitado = valor_solicitado
        self.gasto_dia = gasto_dia
        self.gasto_mes = gasto_mes


def _tz() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "ORCAMENTO_TIMEZONE", "America/Sao_Paulo"))


def inicio_dia(agora):
    local = agora.astimezone(_tz())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def inicio_mes(agora):
    local = agora.astimezone(_tz()).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return local


def gasto_periodo(inicio, fim) -> Decimal:
    conciliadas = (
        ChamadaIA.objects.filter(custo__isnull=False, iniciada_em__gte=inicio, iniciada_em__lt=fim)
        .aggregate(total=Sum("custo"))
        .get("total")
        or ZERO
    )
    reservas = (
        ReservaOrcamento.objects.filter(
            estado=EstadoReserva.ATIVA, criada_em__gte=inicio, criada_em__lt=fim
        )
        .aggregate(total=Sum("valor_estimado"))
        .get("total")
        or ZERO
    )
    return conciliadas + reservas


def gasto_dia(agora=None) -> Decimal:
    agora = agora or timezone.now()
    return gasto_periodo(inicio_dia(agora), agora)


def gasto_mes(agora=None) -> Decimal:
    agora = agora or timezone.now()
    return gasto_periodo(inicio_mes(agora), agora)


def estimativa_padrao() -> Decimal:
    return Decimal(getattr(settings, "AI_CUSTO_ESTIMADO_PADRAO", "0.02"))


def verificar_disponivel(valor_estimado: Decimal, agora=None):
    agora = agora or timezone.now()
    config = ConfiguracaoOrcamento.get_solo()
    dia = gasto_dia(agora)
    mes = gasto_mes(agora)
    if dia + valor_estimado > config.limite_diario:
        raise OrcamentoExcedido("diario", valor_estimado, dia, mes)
    if mes + valor_estimado > config.limite_mensal:
        raise OrcamentoExcedido("mensal", valor_estimado, dia, mes)
    return dia, mes


def reservar(valor_estimado: Decimal, provedor: str = "", modelo: str = "") -> ReservaOrcamento:
    config = ConfiguracaoOrcamento.get_solo()
    try:
        verificar_disponivel(valor_estimado)
    except OrcamentoExcedido as exc:
        EventoOrcamento.objects.create(
            tipo=EventoOrcamento.Tipo.BLOQUEIO,
            limite_atingido=exc.limite_atingido,
            valor_solicitado=valor_estimado,
            gasto_dia=exc.gasto_dia,
            gasto_mes=exc.gasto_mes,
            detalhe=str(exc),
        )
        raise
    ttl = int(getattr(settings, "RESERVA_ORCAMENTO_TTL_SECONDS", 300))
    return ReservaOrcamento.objects.create(
        provedor=provedor,
        modelo=modelo,
        valor_estimado=valor_estimado,
        moeda=config.moeda,
        expira_em=timezone.now() + timedelta(seconds=ttl),
    )


def conciliar(reserva: ReservaOrcamento, chamada: ChamadaIA) -> ReservaOrcamento:
    reserva.chamada = chamada
    reserva.estado = EstadoReserva.CONCILIADA
    reserva.conciliada_em = timezone.now()
    reserva.save(update_fields=["chamada", "estado", "conciliada_em"])
    return reserva


def expirar_reservas(agora=None) -> int:
    agora = agora or timezone.now()
    return ReservaOrcamento.objects.filter(
        estado=EstadoReserva.ATIVA, expira_em__lt=agora
    ).update(estado=EstadoReserva.EXPIRADA)


def _filtrar(filtros: dict):
    qs = ChamadaIA.objects.all()
    if filtros.get("inicio"):
        qs = qs.filter(iniciada_em__gte=filtros["inicio"])
    if filtros.get("fim"):
        qs = qs.filter(iniciada_em__lt=filtros["fim"])
    for campo in ("provedor", "modelo", "finalidade", "status", "conteudo_id", "tarefa_id"):
        if filtros.get(campo) is not None:
            qs = qs.filter(**{campo: filtros[campo]})
    if filtros.get("tentativa") is not None:
        qs = qs.filter(tentativa=filtros["tentativa"])
    return qs


def resumo(filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    qs = _filtrar(filtros)
    total = qs.aggregate(total=Sum("custo")).get("total") or ZERO
    por_provedor = {
        linha["provedor"]: linha["total"] or ZERO
        for linha in qs.values("provedor").annotate(total=Sum("custo"))
    }
    por_modelo = {
        linha["modelo"]: linha["total"] or ZERO
        for linha in qs.values("modelo").annotate(total=Sum("custo"))
    }
    por_finalidade = {
        linha["finalidade"]: linha["total"] or ZERO
        for linha in qs.values("finalidade").annotate(total=Sum("custo"))
    }
    por_dia = {}
    for chamada in qs.filter(custo__isnull=False):
        dia = chamada.iniciada_em.astimezone(_tz()).date().isoformat()
        por_dia[dia] = por_dia.get(dia, ZERO) + chamada.custo
    return {
        "total": total,
        "por_provedor": por_provedor,
        "por_modelo": por_modelo,
        "por_finalidade": por_finalidade,
        "por_dia": por_dia,
        "quantidade": qs.count(),
    }


CSV_CABECALHO = [
    "id",
    "iniciada_em",
    "provedor",
    "modelo",
    "finalidade",
    "etapa",
    "status",
    "tentativa",
    "request_id_externo",
    "tokens_entrada",
    "tokens_saida",
    "tokens_cache",
    "moeda",
    "custo",
    "origem_custo",
    "tarefa_id",
    "conteudo_id",
]


def exportar_csv(filtros: dict | None = None) -> str:
    filtros = filtros or {}
    buff = io.StringIO()
    escritor = csv.writer(buff)
    escritor.writerow(CSV_CABECALHO)
    for chamada in _filtrar(filtros).order_by("iniciada_em"):
        escritor.writerow(
            [
                chamada.pk,
                chamada.iniciada_em.astimezone(_tz()).isoformat(),
                chamada.provedor,
                chamada.modelo,
                chamada.finalidade,
                chamada.etapa,
                chamada.status,
                chamada.tentativa,
                chamada.request_id_externo,
                chamada.tokens_entrada,
                chamada.tokens_saida,
                chamada.tokens_cache,
                chamada.moeda,
                "" if chamada.custo is None else str(chamada.custo),
                chamada.origem_custo,
                chamada.tarefa_id,
                chamada.conteudo_id,
            ]
        )
    return buff.getvalue()
