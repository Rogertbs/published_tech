from django.db import models


class EstadoExecucao(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    EM_EXECUCAO = "em_execucao", "Em execução"
    CONCLUIDA = "concluida", "Concluída"
    FALHOU_PARCIAL = "falhou_parcial", "Falhou (parcial)"
    FALHOU = "falhou", "Falhou"
    CANCELADA = "cancelada", "Cancelada"


class Execucao(models.Model):
    tipo = models.CharField(max_length=64, default="pipeline")
    estado = models.CharField(
        max_length=16, choices=EstadoExecucao.choices, default=EstadoExecucao.PENDENTE
    )
    secao = models.CharField(max_length=32, blank=True, default="")
    tarefa = models.ForeignKey(
        "jobs.Tarefa", null=True, blank=True, on_delete=models.SET_NULL, related_name="execucoes"
    )
    snapshot_config = models.ForeignKey(
        "configuracao.SnapshotConfiguracao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="execucoes",
    )
    iniciado_em = models.DateTimeField(null=True, blank=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    motivo = models.TextField(blank=True, default="")
    erro = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Execucao#{self.pk} [{self.estado}]"


class EtapaExecucao(models.Model):
    execucao = models.ForeignKey(Execucao, on_delete=models.CASCADE, related_name="etapas")
    nome = models.CharField(max_length=32)
    saida = models.JSONField(default=dict, blank=True)
    concluida_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["execucao", "nome"], name="uniq_etapa_execucao_nome")
        ]

    def __str__(self):
        return f"{self.execucao_id}:{self.nome}"


class Evidencia(models.Model):
    execucao = models.ForeignKey(
        Execucao, null=True, blank=True, on_delete=models.SET_NULL, related_name="evidencias"
    )
    versao = models.ForeignKey(
        "content.Versao", null=True, blank=True, on_delete=models.SET_NULL, related_name="evidencias"
    )
    fonte = models.ForeignKey(
        "sources.Fonte", null=True, blank=True, on_delete=models.SET_NULL, related_name="evidencias"
    )
    registro = models.ForeignKey(
        "sources.RegistroNormalizado",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidencias",
    )
    tipo = models.CharField(max_length=32, blank=True, default="")
    url = models.URLField(max_length=500, blank=True, default="")
    trecho = models.TextField(blank=True, default="")
    verificado = models.BooleanField(default=False)
    coletado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Evidencia#{self.pk} {self.url}"
