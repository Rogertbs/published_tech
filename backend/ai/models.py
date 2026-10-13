from django.db import models


class StatusChamada(models.TextChoices):
    SUCESSO = "sucesso", "Sucesso"
    ERRO = "erro", "Erro"
    TIMEOUT = "timeout", "Timeout"
    INCERTO = "incerto", "Incerto"


class OrigemCusto(models.TextChoices):
    INFORMADO = "informado", "Informado"
    ESTIMADO = "estimado", "Estimado"
    RECONCILIADO = "reconciliado", "Reconciliado"
    DESCONHECIDO = "desconhecido", "Desconhecido"


class PrecoModelo(models.Model):
    provedor = models.CharField(max_length=64, verbose_name="provedor")
    modelo = models.CharField(max_length=200, verbose_name="modelo")
    moeda = models.CharField(max_length=8, default="USD", verbose_name="moeda")
    preco_entrada_por_milhao = models.DecimalField(
        max_digits=12, decimal_places=6, verbose_name="preço de entrada (por milhão)"
    )
    preco_saida_por_milhao = models.DecimalField(
        max_digits=12, decimal_places=6, verbose_name="preço de saída (por milhão)"
    )
    vigente_de = models.DateTimeField(verbose_name="vigente de")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        ordering = ["-vigente_de"]
        verbose_name = "preço de modelo"
        verbose_name_plural = "preços de modelo"
        constraints = [
            models.UniqueConstraint(
                fields=["provedor", "modelo", "vigente_de"], name="uniq_preco_provedor_modelo_vigencia"
            )
        ]

    def __str__(self):
        return f"{self.provedor}/{self.modelo} @ {self.vigente_de:%Y-%m-%d}"


class ChamadaIA(models.Model):
    provedor = models.CharField(max_length=64, verbose_name="provedor")
    modelo = models.CharField(max_length=200, verbose_name="modelo")
    finalidade = models.CharField(max_length=64, verbose_name="finalidade")
    etapa = models.CharField(max_length=64, blank=True, default="", verbose_name="etapa")
    tarefa = models.ForeignKey(
        "jobs.Tarefa",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chamadas_ia",
        verbose_name="tarefa",
    )
    execucao = models.ForeignKey(
        "pipeline.Execucao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chamadas_ia",
        verbose_name="execução",
    )
    conteudo_id = models.IntegerField(null=True, blank=True, verbose_name="conteúdo")
    correlacao = models.JSONField(default=dict, blank=True, verbose_name="correlação")

    iniciada_em = models.DateTimeField(verbose_name="iniciada em")
    finalizada_em = models.DateTimeField(null=True, blank=True, verbose_name="finalizada em")
    duracao_ms = models.IntegerField(null=True, blank=True, verbose_name="duração (ms)")
    status = models.CharField(
        max_length=16, choices=StatusChamada.choices, db_index=True, verbose_name="status"
    )
    tentativa = models.PositiveIntegerField(default=1, verbose_name="tentativa")
    request_id_externo = models.CharField(
        max_length=200, blank=True, default="", verbose_name="id externo da requisição"
    )

    tokens_entrada = models.IntegerField(null=True, blank=True, verbose_name="tokens de entrada")
    tokens_saida = models.IntegerField(null=True, blank=True, verbose_name="tokens de saída")
    tokens_cache = models.IntegerField(null=True, blank=True, verbose_name="tokens de cache")
    unidades_imagem = models.IntegerField(null=True, blank=True, verbose_name="unidades de imagem")
    resolucao = models.CharField(max_length=32, blank=True, default="", verbose_name="resolução")

    moeda = models.CharField(max_length=8, default="USD", verbose_name="moeda")
    preco_aplicado = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True, verbose_name="preço aplicado"
    )
    custo = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True, verbose_name="custo"
    )
    origem_custo = models.CharField(
        max_length=16,
        choices=OrigemCusto.choices,
        default=OrigemCusto.DESCONHECIDO,
        verbose_name="origem do custo",
    )

    erro = models.TextField(blank=True, default="", verbose_name="erro")
    criada_em = models.DateTimeField(auto_now_add=True, verbose_name="criada em")

    class Meta:
        ordering = ["-iniciada_em"]
        verbose_name = "chamada de IA"
        verbose_name_plural = "chamadas de IA"
        indexes = [models.Index(fields=["finalidade", "status"])]

    def __str__(self):
        return f"ChamadaIA#{self.pk} {self.provedor}/{self.modelo} [{self.status}]"

    def as_dict(self) -> dict:
        return {
            "id": self.pk,
            "provedor": self.provedor,
            "modelo": self.modelo,
            "finalidade": self.finalidade,
            "status": self.status,
            "tokens_entrada": self.tokens_entrada,
            "tokens_saida": self.tokens_saida,
            "custo": str(self.custo) if self.custo is not None else None,
            "moeda": self.moeda,
            "origem_custo": self.origem_custo,
            "duracao_ms": self.duracao_ms,
        }
