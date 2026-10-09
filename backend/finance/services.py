from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

from ai.models import ChamadaIA, OrigemCusto, StatusChamada
from finance.models import ConfiguracaoOrcamento, EstadoReserva, EventoOrcamento, ReservaOrcamento

ZERO = Decimal("0")


class OrcamentoExcedido(Exception):
    def __init__(self, limite_atingido, valor_solicitado, gasto_dia, gasto_mes):
        super().__init__(f"Orçamento {limite_atingido} excedido.")
        self.limite_atingido = limite_atingido
        self.valor_solicitado = valor_solicitado
        self.gasto_dia = gasto_dia
        self.gasto_mes = gasto_mes


def tz_local() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "ORCAMENTO_TIMEZONE", "America/Sao_Paulo"))


def inicio_dia(agora):
    local = agora.astimezone(tz_local())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def inicio_mes(agora):
    local = agora.astimezone(tz_local()).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return local


def estimativa_padrao() -> Decimal:
    return Decimal(getattr(settings, "AI_CUSTO_ESTIMADO_PADRAO", "0.02"))


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


def expirar_reservas(agora=None) -> int:
    agora = agora or timezone.now()
    return ReservaOrcamento.objects.filter(
        estado=EstadoReserva.ATIVA, expira_em__lt=agora
    ).update(estado=EstadoReserva.EXPIRADA)


def gasto_dia(agora=None) -> Decimal:
    agora = agora or timezone.now()
    expirar_reservas(agora)
    return gasto_periodo(inicio_dia(agora), agora)


def gasto_mes(agora=None) -> Decimal:
    agora = agora or timezone.now()
    expirar_reservas(agora)
    return gasto_periodo(inicio_mes(agora), agora)


def _verificar(config, valor_estimado, agora):
    dia = gasto_dia(agora)
    mes = gasto_mes(agora)
    if dia + valor_estimado > config.limite_diario:
        raise OrcamentoExcedido("diario", valor_estimado, dia, mes)
    if mes + valor_estimado > config.limite_mensal:
        raise OrcamentoExcedido("mensal", valor_estimado, dia, mes)


def verificar_disponivel(valor_estimado: Decimal, agora=None):
    agora = agora or timezone.now()
    return _verificar(ConfiguracaoOrcamento.get_solo(), valor_estimado, agora)


def _config_lockada() -> ConfiguracaoOrcamento:
    ConfiguracaoOrcamento.get_solo()
    qs = ConfiguracaoOrcamento.objects.all()
    if connection.vendor == "postgresql":
        qs = qs.select_for_update()
    return qs.get(pk=1)


def reservar(valor_estimado: Decimal, provedor: str = "", modelo: str = "") -> ReservaOrcamento:
    agora = timezone.now()
    expirar_reservas(agora)
    try:
        with transaction.atomic():
            config = _config_lockada()
            _verificar(config, valor_estimado, agora)
            ttl = int(getattr(settings, "RESERVA_ORCAMENTO_TTL_SECONDS", 300))
            return ReservaOrcamento.objects.create(
                provedor=provedor,
                modelo=modelo,
                valor_estimado=valor_estimado,
                moeda=config.moeda,
                expira_em=agora + timedelta(seconds=ttl),
            )
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


def conciliar(reserva: ReservaOrcamento, chamada: ChamadaIA) -> ReservaOrcamento:
    if chamada.custo is None and chamada.status in (StatusChamada.INCERTO, StatusChamada.TIMEOUT):
        chamada.custo = reserva.valor_estimado
        chamada.origem_custo = OrigemCusto.ESTIMADO
        chamada.moeda = reserva.moeda
        chamada.save(update_fields=["custo", "origem_custo", "moeda"])

    reserva.chamada = chamada
    reserva.estado = EstadoReserva.CONCILIADA
    reserva.conciliada_em = timezone.now()
    reserva.save(update_fields=["chamada", "estado", "conciliada_em"])
    return reserva
