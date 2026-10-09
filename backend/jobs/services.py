import os
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from jobs.handlers import get_handler
from jobs.models import (
    Agendamento,
    ConfiguracaoMotor,
    EstadoTarefa,
    EventoTarefa,
    NivelEvento,
    OrigemTarefa,
    Tarefa,
)

ATIVOS = [EstadoTarefa.RESERVADA, EstadoTarefa.EM_EXECUCAO]


class ReservaInvalida(Exception):
    pass


class MotorPausado(Exception):
    pass


def _lease_seconds() -> int:
    return int(getattr(settings, "JOBS_LEASE_SECONDS", 60))


def _backoff_seconds(tentativa: int) -> int:
    base = int(getattr(settings, "JOBS_BACKOFF_BASE", 30))
    factor = int(getattr(settings, "JOBS_BACKOFF_FACTOR", 4))
    return base * (factor ** max(0, tentativa - 1))


def _para_reserva(qs):
    if connection.vendor == "postgresql":
        return qs.select_for_update(skip_locked=True)
    return qs


def _reverter_para_fila(tarefa: Tarefa, token: str, *, erro=None, reagendar_para=None) -> int:
    campos = dict(
        estado=EstadoTarefa.PENDENTE,
        reserva_token=None,
        lease_expira_em=None,
        worker="",
        interrupcao_solicitada=False,
    )
    if reagendar_para is not None:
        campos["agendado_para"] = reagendar_para
    else:
        campos["tentativas"] = max(0, tarefa.tentativas - 1)
    if erro is not None:
        campos["erro"] = erro
    return Tarefa.objects.filter(pk=tarefa.pk, reserva_token=token, estado__in=ATIVOS).update(**campos)


def registrar_evento(tarefa: Tarefa, mensagem: str, nivel: str = NivelEvento.INFO) -> None:
    EventoTarefa.objects.create(tarefa=tarefa, mensagem=mensagem, nivel=nivel)


def reservar_proxima(worker_id: str, agora=None) -> Tarefa | None:
    agora = agora or timezone.now()
    with transaction.atomic():
        base = Tarefa.objects.filter(
            estado=EstadoTarefa.PENDENTE, agendado_para__lte=agora
        ).order_by("-prioridade", "agendado_para", "id")
        tarefa = _para_reserva(base).first()
        if tarefa is None:
            return None

        token = uuid.uuid4().hex
        atualizadas = Tarefa.objects.filter(pk=tarefa.pk, estado=EstadoTarefa.PENDENTE).update(
            estado=EstadoTarefa.RESERVADA,
            reserva_token=token,
            worker=worker_id,
            lease_expira_em=agora + timedelta(seconds=_lease_seconds()),
            tentativas=tarefa.tentativas + 1,
            iniciado_em=agora,
            interrupcao_solicitada=False,
        )
        if not atualizadas:
            return None

    tarefa.refresh_from_db()
    registrar_evento(tarefa, f"reservada por {worker_id} (tentativa {tarefa.tentativas})")
    return tarefa


def concluir(tarefa: Tarefa, token: str, resultado=None) -> None:
    if tarefa.reserva_token != token:
        raise ReservaInvalida("Token de reserva inválido para concluir.")
    atualizadas = Tarefa.objects.filter(pk=tarefa.pk, reserva_token=token, estado__in=ATIVOS).update(
        estado=EstadoTarefa.CONCLUIDA,
        finalizado_em=timezone.now(),
        reserva_token=None,
        lease_expira_em=None,
        erro="",
        resultado=resultado or {},
    )
    if not atualizadas:
        raise ReservaInvalida("Reserva não está mais ativa.")
    registrar_evento(tarefa, "concluída")


def falhar(tarefa: Tarefa, token: str, erro: str) -> None:
    if tarefa.reserva_token != token:
        raise ReservaInvalida("Token de reserva inválido para falhar.")
    tarefa.refresh_from_db()
    if tarefa.tentativas < tarefa.limite_tentativas:
        quando = timezone.now() + timedelta(seconds=_backoff_seconds(tarefa.tentativas))
        atualizadas = _reverter_para_fila(tarefa, token, erro=erro, reagendar_para=quando)
        pode_retentar = True
    else:
        atualizadas = Tarefa.objects.filter(pk=tarefa.pk, reserva_token=token, estado__in=ATIVOS).update(
            estado=EstadoTarefa.FALHOU,
            finalizado_em=timezone.now(),
            reserva_token=None,
            lease_expira_em=None,
            erro=erro,
        )
        pode_retentar = False
    if not atualizadas:
        raise ReservaInvalida("Reserva não está mais ativa.")
    registrar_evento(tarefa, f"falhou: {erro}", nivel=NivelEvento.ERRO)
    if pode_retentar:
        registrar_evento(tarefa, f"reagendada para retry em {quando.isoformat()}")


def recuperar_abandonadas(agora=None) -> int:
    agora = agora or timezone.now()
    recuperadas = 0
    qs = Tarefa.objects.filter(estado__in=ATIVOS, lease_expira_em__lt=agora)
    for tarefa in qs:
        if tarefa.tentativas >= tarefa.limite_tentativas:
            atualizadas = Tarefa.objects.filter(
                pk=tarefa.pk, reserva_token=tarefa.reserva_token, estado__in=ATIVOS
            ).update(
                estado=EstadoTarefa.ABANDONADA,
                finalizado_em=agora,
                reserva_token=None,
                lease_expira_em=None,
                interrupcao_solicitada=False,
            )
            mensagem, nivel = "abandonada (lease expirado, sem tentativas)", NivelEvento.ERRO
        else:
            atualizadas = Tarefa.objects.filter(
                pk=tarefa.pk, reserva_token=tarefa.reserva_token, estado__in=ATIVOS
            ).update(
                estado=EstadoTarefa.PENDENTE,
                reserva_token=None,
                lease_expira_em=None,
                worker="",
                interrupcao_solicitada=False,
            )
            mensagem, nivel = "devolvida à fila (lease expirado)", NivelEvento.INFO
        if atualizadas:
            registrar_evento(tarefa, mensagem, nivel=nivel)
            recuperadas += 1
    return recuperadas


def executar(tarefa: Tarefa) -> None:
    token = tarefa.reserva_token
    if tarefa.interrupcao_solicitada:
        _reverter_para_fila(tarefa, token)
        registrar_evento(tarefa, "suspensa antes de executar (interrupção solicitada)")
        return

    atualizadas = Tarefa.objects.filter(
        pk=tarefa.pk, reserva_token=token, estado=EstadoTarefa.RESERVADA
    ).update(estado=EstadoTarefa.EM_EXECUCAO)
    if not atualizadas:
        raise ReservaInvalida("Reserva não está mais ativa.")
    registrar_evento(tarefa, "em execução")

    handler = get_handler(tarefa.tipo_tarefa)
    if handler is None:
        falhar(tarefa, token, f"Sem handler registrado para '{tarefa.tipo_tarefa}'.")
        return
    try:
        resultado = handler(tarefa) or {}
    except Exception as exc:
        falhar(tarefa, token, str(exc))
        return
    concluir(tarefa, token, resultado)


def processar_uma(worker_id: str | None = None, agora=None) -> bool:
    worker_id = worker_id or f"worker-{os.getpid()}"
    tarefa = reservar_proxima(worker_id, agora)
    if tarefa is None:
        return False
    motor = ConfiguracaoMotor.get_solo()
    if (motor.pausado and tarefa.origem == OrigemTarefa.AUTOMATICO) or tarefa.interrupcao_solicitada:
        _reverter_para_fila(tarefa, tarefa.reserva_token)
        registrar_evento(tarefa, "suspensa (motor pausado)")
        return False
    executar(tarefa)
    return True


def rodar_agendador(agora=None) -> int:
    agora = agora or timezone.now()
    motor = ConfiguracaoMotor.get_solo()
    if motor.pausado or not motor.automatico:
        return 0

    criadas = 0
    with transaction.atomic():
        qs = _para_reserva(
            Agendamento.objects.filter(ativo=True, proxima_execucao__lte=agora)
        )
        for agendamento in qs:
            chave = f"ag:{agendamento.pk}:{agendamento.proxima_execucao.isoformat()}"
            _, created = Tarefa.objects.get_or_create(
                chave_idempotencia=chave,
                defaults={
                    "tipo_tarefa": agendamento.tipo_tarefa,
                    "parametros": agendamento.parametros,
                    "origem": OrigemTarefa.AUTOMATICO,
                    "agendado_para": agendamento.proxima_execucao,
                },
            )
            while agendamento.proxima_execucao <= agora:
                agendamento.proxima_execucao = agendamento.proxima_execucao + timedelta(
                    seconds=agendamento.intervalo_segundos
                )
            agendamento.save(update_fields=["proxima_execucao"])
            if created:
                criadas += 1
    return criadas


def executar_agora(tipo_tarefa: str, parametros=None, chave=None) -> tuple[Tarefa, bool]:
    if ConfiguracaoMotor.get_solo().pausado:
        raise MotorPausado("Motor pausado: não é possível executar.")
    chave = chave or f"manual:{uuid.uuid4().hex}"
    with transaction.atomic():
        tarefa, created = Tarefa.objects.get_or_create(
            chave_idempotencia=chave,
            defaults={
                "tipo_tarefa": tipo_tarefa,
                "parametros": parametros or {},
                "origem": OrigemTarefa.MANUAL,
            },
        )
    if created:
        registrar_evento(tarefa, "enfileirada manualmente")
    return tarefa, created


def pausar() -> int:
    motor = ConfiguracaoMotor.get_solo()
    motor.pausado = True
    motor.save(update_fields=["pausado", "atualizado_em"])

    Tarefa.objects.filter(estado__in=ATIVOS, origem=OrigemTarefa.AUTOMATICO).update(
        interrupcao_solicitada=True
    )

    pendentes = Tarefa.objects.filter(estado=EstadoTarefa.PENDENTE, origem=OrigemTarefa.AUTOMATICO)
    canceladas = 0
    for tarefa in pendentes:
        Tarefa.objects.filter(pk=tarefa.pk, estado=EstadoTarefa.PENDENTE).update(
            estado=EstadoTarefa.CANCELADA, finalizado_em=timezone.now()
        )
        registrar_evento(tarefa, "cancelada: motor pausado")
        canceladas += 1
    return canceladas


def ativar() -> None:
    motor = ConfiguracaoMotor.get_solo()
    motor.pausado = False
    motor.save(update_fields=["pausado", "atualizado_em"])


def definir_automatico(valor: bool) -> None:
    motor = ConfiguracaoMotor.get_solo()
    motor.automatico = valor
    motor.save(update_fields=["automatico", "atualizado_em"])


def expirar_eventos(antes_de) -> int:
    removidos, _ = EventoTarefa.objects.filter(criado_em__lt=antes_de).delete()
    return removidos
