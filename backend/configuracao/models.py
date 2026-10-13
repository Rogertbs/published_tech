from django.conf import settings
from django.db import models


class EscopoConfig(models.TextChoices):
    SISTEMA = "sistema", "Sistema"
    GERAL = "geral", "Geral"
    SECAO = "secao", "Seção"
    AGENTE = "agente", "Agente"


class Configuracao(models.Model):
    chave = models.CharField(max_length=120, unique=True, verbose_name="chave")
    escopo = models.CharField(max_length=16, choices=EscopoConfig.choices, verbose_name="escopo")
    secao = models.CharField(max_length=64, blank=True, default="", verbose_name="seção")
    agente = models.CharField(max_length=64, blank=True, default="", verbose_name="agente")
    descricao = models.TextField(blank=True, default="", verbose_name="descrição")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criada em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="atualizada em")

    class Meta:
        ordering = ["escopo", "chave"]
        verbose_name = "configuração"
        verbose_name_plural = "configurações"
        constraints = [
            models.UniqueConstraint(
                fields=["escopo", "secao", "agente"], name="uniq_config_escopo_alvo"
            )
        ]

    def __str__(self):
        return self.chave


class VersaoConfiguracao(models.Model):
    configuracao = models.ForeignKey(
        Configuracao, on_delete=models.CASCADE, related_name="versoes", verbose_name="configuração"
    )
    numero = models.PositiveIntegerField(verbose_name="número")
    campos = models.JSONField(default=dict, verbose_name="campos")
    ativa = models.BooleanField(default=False, verbose_name="ativa")
    criada_em = models.DateTimeField(auto_now_add=True, verbose_name="criada em")
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="criada por",
    )

    class Meta:
        ordering = ["-numero"]
        verbose_name = "versão de configuração"
        verbose_name_plural = "versões de configuração"
        constraints = [
            models.UniqueConstraint(
                fields=["configuracao", "numero"], name="uniq_versao_config_numero"
            )
        ]

    def __str__(self):
        return f"{self.configuracao.chave} v{self.numero}"


class SnapshotConfiguracao(models.Model):
    tarefa = models.ForeignKey(
        "jobs.Tarefa",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="snapshots_config",
        verbose_name="tarefa",
    )
    campos = models.JSONField(default=dict, verbose_name="campos")
    versoes = models.JSONField(default=dict, verbose_name="versões")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "snapshot de configuração"
        verbose_name_plural = "snapshots de configuração"

    def __str__(self):
        return f"Snapshot#{self.pk}"
