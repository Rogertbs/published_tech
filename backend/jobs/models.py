from django.db import models
from django.utils import timezone


class EstadoTarefa(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    RESERVADA = "reservada", "Reservada"
    EM_EXECUCAO = "em_execucao", "Em execução"
    CONCLUIDA = "concluida", "Concluída"
    FALHOU = "falhou", "Falhou"
    CANCELADA = "cancelada", "Cancelada"
    ABANDONADA = "abandonada", "Abandonada"


class OrigemTarefa(models.TextChoices):
    AUTOMATICO = "automatico", "Automático"
    MANUAL = "manual", "Manual"


class Tarefa(models.Model):
    tipo_tarefa = models.CharField(max_length=64, verbose_name="tipo de tarefa")
    parametros = models.JSONField(default=dict, blank=True, verbose_name="parâmetros")
    prioridade = models.IntegerField(default=0, verbose_name="prioridade")
    agendado_para = models.DateTimeField(default=timezone.now, verbose_name="agendado para")
    estado = models.CharField(
        max_length=16,
        choices=EstadoTarefa.choices,
        default=EstadoTarefa.PENDENTE,
        db_index=True,
        verbose_name="estado",
    )
    origem = models.CharField(
        max_length=16,
        choices=OrigemTarefa.choices,
        default=OrigemTarefa.MANUAL,
        verbose_name="origem",
    )
    tentativas = models.PositiveIntegerField(default=0, verbose_name="tentativas")
    limite_tentativas = models.PositiveIntegerField(default=3, verbose_name="limite de tentativas")
    iniciado_em = models.DateTimeField(null=True, blank=True, verbose_name="iniciado em")
    finalizado_em = models.DateTimeField(null=True, blank=True, verbose_name="finalizado em")
    worker = models.CharField(max_length=128, blank=True, default="", verbose_name="worker")
    reserva_token = models.CharField(
        max_length=64, null=True, blank=True, verbose_name="token de reserva"
    )
    lease_expira_em = models.DateTimeField(null=True, blank=True, verbose_name="lease expira em")
    interrupcao_solicitada = models.BooleanField(
        default=False, verbose_name="interrupção solicitada"
    )
    erro = models.TextField(blank=True, default="", verbose_name="erro")
    resultado = models.JSONField(null=True, blank=True, verbose_name="resultado")
    chave_idempotencia = models.CharField(
        max_length=200, unique=True, null=True, blank=True, verbose_name="chave de idempotência"
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criada em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="atualizada em")

    class Meta:
        ordering = ["-prioridade", "agendado_para", "id"]
        verbose_name = "tarefa"
        verbose_name_plural = "tarefas"
        indexes = [models.Index(fields=["estado", "agendado_para"])]

    def __str__(self):
        return f"Tarefa#{self.pk} {self.tipo_tarefa} [{self.estado}]"

    def as_dict(self) -> dict:
        return {
            "id": self.pk,
            "tipo": self.tipo_tarefa,
            "estado": self.estado,
            "origem": self.origem,
            "tentativas": self.tentativas,
            "resultado": self.resultado,
            "erro": self.erro,
        }


class NivelEvento(models.TextChoices):
    INFO = "info", "Info"
    ERRO = "erro", "Erro"


class EventoTarefa(models.Model):
    tarefa = models.ForeignKey(
        Tarefa, on_delete=models.CASCADE, related_name="eventos", verbose_name="tarefa"
    )
    nivel = models.CharField(
        max_length=8, choices=NivelEvento.choices, default=NivelEvento.INFO, verbose_name="nível"
    )
    mensagem = models.TextField(verbose_name="mensagem")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        ordering = ["id"]
        verbose_name = "evento de tarefa"
        verbose_name_plural = "eventos de tarefa"

    def __str__(self):
        return f"[{self.nivel}] {self.mensagem}"


class Agendamento(models.Model):
    tipo_tarefa = models.CharField(max_length=64, verbose_name="tipo de tarefa")
    parametros = models.JSONField(default=dict, blank=True, verbose_name="parâmetros")
    intervalo_segundos = models.PositiveIntegerField(verbose_name="intervalo (segundos)")
    ativo = models.BooleanField(default=True, verbose_name="ativo")
    proxima_execucao = models.DateTimeField(verbose_name="próxima execução")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        ordering = ["proxima_execucao"]
        verbose_name = "agendamento"
        verbose_name_plural = "agendamentos"

    def __str__(self):
        return f"Agendamento#{self.pk} {self.tipo_tarefa} a cada {self.intervalo_segundos}s"


class ConfiguracaoMotor(models.Model):
    pausado = models.BooleanField(default=False, verbose_name="pausado")
    automatico = models.BooleanField(default=False, verbose_name="automático")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="atualizado em")

    class Meta:
        verbose_name = "Configuração do motor"
        verbose_name_plural = "Configuração do motor"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "ConfiguracaoMotor":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Motor"
