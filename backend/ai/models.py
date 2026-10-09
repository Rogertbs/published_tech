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
    provedor = models.CharField(max_length=64)
    modelo = models.CharField(max_length=200)
    moeda = models.CharField(max_length=8, default="USD")
    preco_entrada_por_milhao = models.DecimalField(max_digits=12, decimal_places=6)
    preco_saida_por_milhao = models.DecimalField(max_digits=12, decimal_places=6)
    vigente_de = models.DateTimeField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-vigente_de"]
        constraints = [
            models.UniqueConstraint(
                fields=["provedor", "modelo", "vigente_de"], name="uniq_preco_provedor_modelo_vigencia"
            )
        ]

    def __str__(self):
        return f"{self.provedor}/{self.modelo} @ {self.vigente_de:%Y-%m-%d}"


class ChamadaIA(models.Model):
    provedor = models.CharField(max_length=64)
    modelo = models.CharField(max_length=200)
    finalidade = models.CharField(max_length=64)
    etapa = models.CharField(max_length=64, blank=True, default="")
    tarefa = models.ForeignKey(
        "jobs.Tarefa", null=True, blank=True, on_delete=models.SET_NULL, related_name="chamadas_ia"
    )
    conteudo_id = models.IntegerField(null=True, blank=True)
    correlacao = models.JSONField(default=dict, blank=True)

    iniciada_em = models.DateTimeField()
    finalizada_em = models.DateTimeField(null=True, blank=True)
    duracao_ms = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=StatusChamada.choices, db_index=True)
    tentativa = models.PositiveIntegerField(default=1)
    request_id_externo = models.CharField(max_length=200, blank=True, default="")

    tokens_entrada = models.IntegerField(null=True, blank=True)
    tokens_saida = models.IntegerField(null=True, blank=True)
    tokens_cache = models.IntegerField(null=True, blank=True)
    unidades_imagem = models.IntegerField(null=True, blank=True)
    resolucao = models.CharField(max_length=32, blank=True, default="")

    moeda = models.CharField(max_length=8, default="USD")
    preco_aplicado = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    custo = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    origem_custo = models.CharField(max_length=16, choices=OrigemCusto.choices, default=OrigemCusto.DESCONHECIDO)

    erro = models.TextField(blank=True, default="")
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-iniciada_em"]
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
