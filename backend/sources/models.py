from django.db import models


class TipoFonte(models.TextChoices):
    GITHUB = "github", "GitHub"
    HUGGINGFACE = "huggingface", "Hugging Face"


class CategoriaModelo(models.TextChoices):
    LANCAMENTO_CONFIRMADO = "lancamento_confirmado", "Lançamento confirmado"
    NOVA_VARIANTE = "nova_variante", "Nova variante/quantização/fine-tuning"
    MODELO_ANTIGO_ATENCAO = "modelo_antigo_atencao", "Modelo antigo que ganhou atenção"
    ATUALIZACAO_REPOSITORIO = "atualizacao_repositorio", "Atualização de repositório sem lançamento"


class EstadoColeta(models.TextChoices):
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    OK = "ok", "OK"
    FALHOU_PARCIAL = "falhou_parcial", "Falhou (parcial)"
    FALHOU = "falhou", "Falhou"


class Fonte(models.Model):
    tipo = models.CharField(max_length=32, choices=TipoFonte.choices)
    nome = models.CharField(max_length=120)
    habilitada = models.BooleanField(default=True)
    credencial_ref = models.CharField(max_length=120, blank=True, default="")
    parametros = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["tipo", "nome"], name="uniq_fonte_tipo_nome")
        ]

    def __str__(self):
        return f"{self.nome} ({self.tipo})"


class Coleta(models.Model):
    fonte = models.ForeignKey(Fonte, on_delete=models.CASCADE, related_name="coletas")
    estado = models.CharField(
        max_length=16, choices=EstadoColeta.choices, default=EstadoColeta.EM_ANDAMENTO
    )
    iniciada_em = models.DateTimeField()
    finalizada_em = models.DateTimeField(null=True, blank=True)
    total_registros = models.PositiveIntegerField(default=0)
    erro = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-iniciada_em"]

    def __str__(self):
        return f"Coleta#{self.pk} {self.fonte.nome} [{self.estado}]"


class RegistroNormalizado(models.Model):
    fonte = models.ForeignKey(Fonte, on_delete=models.CASCADE, related_name="registros")
    coleta = models.ForeignKey(
        Coleta, null=True, blank=True, on_delete=models.SET_NULL, related_name="registros"
    )
    chave_externa = models.CharField(max_length=200)
    dados = models.JSONField(default=dict)
    coletado_em = models.DateTimeField()

    class Meta:
        ordering = ["-coletado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["fonte", "chave_externa"], name="uniq_registro_fonte_chave"
            )
        ]

    def __str__(self):
        return f"{self.fonte.tipo}:{self.chave_externa}"


class Candidato(models.Model):
    registro = models.OneToOneField(
        RegistroNormalizado, on_delete=models.CASCADE, related_name="candidato"
    )
    pontuacao = models.FloatField(default=0)
    motivo = models.TextField(blank=True, default="")
    selecionado = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pontuacao"]

    def __str__(self):
        return f"Candidato({self.registro.chave_externa}) score={self.pontuacao}"
