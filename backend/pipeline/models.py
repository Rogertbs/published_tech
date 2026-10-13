from django.db import models


class EstadoExecucao(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    EM_EXECUCAO = "em_execucao", "Em execução"
    CONCLUIDA = "concluida", "Concluída"
    FALHOU_PARCIAL = "falhou_parcial", "Falhou (parcial)"
    FALHOU = "falhou", "Falhou"
    CANCELADA = "cancelada", "Cancelada"


class Execucao(models.Model):
    tipo = models.CharField(max_length=64, default="pipeline", verbose_name="tipo")
    estado = models.CharField(
        max_length=16,
        choices=EstadoExecucao.choices,
        default=EstadoExecucao.PENDENTE,
        verbose_name="estado",
    )
    secao = models.CharField(max_length=32, blank=True, default="", verbose_name="seção")
    tarefa = models.ForeignKey(
        "jobs.Tarefa",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="execucoes",
        verbose_name="tarefa",
    )
    snapshot_config = models.ForeignKey(
        "configuracao.SnapshotConfiguracao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="execucoes",
        verbose_name="snapshot de configuração",
    )
    iniciado_em = models.DateTimeField(null=True, blank=True, verbose_name="iniciada em")
    finalizado_em = models.DateTimeField(null=True, blank=True, verbose_name="finalizada em")
    motivo = models.TextField(blank=True, default="", verbose_name="motivo")
    erro = models.TextField(blank=True, default="", verbose_name="erro")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criada em")

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "execução"
        verbose_name_plural = "execuções"

    def __str__(self):
        return f"Execucao#{self.pk} [{self.estado}]"


class EtapaExecucao(models.Model):
    execucao = models.ForeignKey(
        Execucao, on_delete=models.CASCADE, related_name="etapas", verbose_name="execução"
    )
    nome = models.CharField(max_length=32, verbose_name="nome")
    saida = models.JSONField(default=dict, blank=True, verbose_name="saída")
    concluida_em = models.DateTimeField(auto_now_add=True, verbose_name="concluída em")

    class Meta:
        ordering = ["id"]
        verbose_name = "etapa de execução"
        verbose_name_plural = "etapas de execução"
        constraints = [
            models.UniqueConstraint(fields=["execucao", "nome"], name="uniq_etapa_execucao_nome")
        ]

    def __str__(self):
        return f"{self.execucao_id}:{self.nome}"


class Evidencia(models.Model):
    execucao = models.ForeignKey(
        Execucao,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidencias",
        verbose_name="execução",
    )
    versao = models.ForeignKey(
        "content.Versao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidencias",
        verbose_name="versão",
    )
    fonte = models.ForeignKey(
        "sources.Fonte",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidencias",
        verbose_name="fonte",
    )
    registro = models.ForeignKey(
        "sources.RegistroNormalizado",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidencias",
        verbose_name="registro",
    )
    tipo = models.CharField(max_length=32, blank=True, default="", verbose_name="tipo")
    url = models.URLField(max_length=500, blank=True, default="", verbose_name="url")
    trecho = models.TextField(blank=True, default="", verbose_name="trecho")
    verificado = models.BooleanField(default=False, verbose_name="verificado")
    coletado_em = models.DateTimeField(null=True, blank=True, verbose_name="coletado em")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criada em")

    class Meta:
        ordering = ["id"]
        verbose_name = "evidência"
        verbose_name_plural = "evidências"

    def __str__(self):
        return f"Evidencia#{self.pk} {self.url}"
