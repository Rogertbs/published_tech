from django.conf import settings
from django.db import models


class EscopoConfig(models.TextChoices):
    SISTEMA = "sistema", "Sistema"
    GERAL = "geral", "Geral"
    SECAO = "secao", "Seção"
    AGENTE = "agente", "Agente"


class Configuracao(models.Model):
    chave = models.CharField(max_length=120, unique=True)
    escopo = models.CharField(max_length=16, choices=EscopoConfig.choices)
    secao = models.CharField(max_length=64, blank=True, default="")
    agente = models.CharField(max_length=64, blank=True, default="")
    descricao = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["escopo", "chave"]
        constraints = [
            models.UniqueConstraint(
                fields=["escopo", "secao", "agente"], name="uniq_config_escopo_alvo"
            )
        ]

    def __str__(self):
        return self.chave


class VersaoConfiguracao(models.Model):
    configuracao = models.ForeignKey(
        Configuracao, on_delete=models.CASCADE, related_name="versoes"
    )
    numero = models.PositiveIntegerField()
    campos = models.JSONField(default=dict)
    ativa = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["-numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["configuracao", "numero"], name="uniq_versao_config_numero"
            )
        ]

    def __str__(self):
        return f"{self.configuracao.chave} v{self.numero}"


class SnapshotConfiguracao(models.Model):
    tarefa = models.ForeignKey(
        "jobs.Tarefa", null=True, blank=True, on_delete=models.SET_NULL, related_name="snapshots_config"
    )
    campos = models.JSONField(default=dict)
    versoes = models.JSONField(default=dict)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Snapshot#{self.pk}"


class AuditoriaAdministrativa(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    acao = models.CharField(max_length=64)
    entidade = models.CharField(max_length=64)
    entidade_id = models.CharField(max_length=64)
    antes = models.JSONField(null=True, blank=True)
    depois = models.JSONField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Auditoria administrativa"
        verbose_name_plural = "Auditoria administrativa"

    def __str__(self):
        return f"{self.acao} {self.entidade}#{self.entidade_id}"
