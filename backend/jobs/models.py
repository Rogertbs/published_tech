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
    tipo_tarefa = models.CharField(max_length=64)
    parametros = models.JSONField(default=dict, blank=True)
    prioridade = models.IntegerField(default=0)
    agendado_para = models.DateTimeField(default=timezone.now)
    estado = models.CharField(
        max_length=16, choices=EstadoTarefa.choices, default=EstadoTarefa.PENDENTE, db_index=True
    )
    origem = models.CharField(
        max_length=16, choices=OrigemTarefa.choices, default=OrigemTarefa.MANUAL
    )
    tentativas = models.PositiveIntegerField(default=0)
    limite_tentativas = models.PositiveIntegerField(default=3)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    worker = models.CharField(max_length=128, blank=True, default="")
    reserva_token = models.CharField(max_length=64, null=True, blank=True)
    lease_expira_em = models.DateTimeField(null=True, blank=True)
    erro = models.TextField(blank=True, default="")
    resultado = models.JSONField(null=True, blank=True)
    chave_idempotencia = models.CharField(max_length=200, unique=True, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-prioridade", "agendado_para", "id"]
        indexes = [models.Index(fields=["estado", "agendado_para"])]

    def __str__(self):
        return f"Tarefa#{self.pk} {self.tipo_tarefa} [{self.estado}]"


class NivelEvento(models.TextChoices):
    INFO = "info", "Info"
    ERRO = "erro", "Erro"


class EventoTarefa(models.Model):
    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name="eventos")
    nivel = models.CharField(max_length=8, choices=NivelEvento.choices, default=NivelEvento.INFO)
    mensagem = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"[{self.nivel}] {self.mensagem}"


class Agendamento(models.Model):
    tipo_tarefa = models.CharField(max_length=64)
    parametros = models.JSONField(default=dict, blank=True)
    intervalo_segundos = models.PositiveIntegerField()
    ativo = models.BooleanField(default=True)
    proxima_execucao = models.DateTimeField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["proxima_execucao"]

    def __str__(self):
        return f"Agendamento#{self.pk} {self.tipo_tarefa} a cada {self.intervalo_segundos}s"


class ConfiguracaoMotor(models.Model):
    pausado = models.BooleanField(default=False)
    automatico = models.BooleanField(default=False)
    atualizado_em = models.DateTimeField(auto_now=True)

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
