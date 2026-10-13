from django.db import models


class TipoFonte(models.TextChoices):
    GITHUB = "github", "GitHub"
    HUGGINGFACE = "huggingface", "Hugging Face"
    RSS = "rss", "RSS (notícias)"


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
    tipo = models.CharField(max_length=32, choices=TipoFonte.choices, verbose_name="tipo")
    nome = models.CharField(max_length=120, verbose_name="nome")
    habilitada = models.BooleanField(default=True, verbose_name="habilitada")
    credencial_ref = models.CharField(
        max_length=120, blank=True, default="", verbose_name="referência da credencial"
    )
    parametros = models.JSONField(default=dict, blank=True, verbose_name="parâmetros")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criada em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="atualizada em")

    class Meta:
        ordering = ["nome"]
        verbose_name = "fonte"
        verbose_name_plural = "fontes"
        constraints = [
            models.UniqueConstraint(fields=["tipo", "nome"], name="uniq_fonte_tipo_nome")
        ]

    def __str__(self):
        return f"{self.nome} ({self.tipo})"


class Coleta(models.Model):
    fonte = models.ForeignKey(
        Fonte, on_delete=models.CASCADE, related_name="coletas", verbose_name="fonte"
    )
    estado = models.CharField(
        max_length=16,
        choices=EstadoColeta.choices,
        default=EstadoColeta.EM_ANDAMENTO,
        verbose_name="estado",
    )
    iniciada_em = models.DateTimeField(verbose_name="iniciada em")
    finalizada_em = models.DateTimeField(null=True, blank=True, verbose_name="finalizada em")
    total_registros = models.PositiveIntegerField(default=0, verbose_name="total de registros")
    erro = models.TextField(blank=True, default="", verbose_name="erro")

    class Meta:
        ordering = ["-iniciada_em"]
        verbose_name = "coleta"
        verbose_name_plural = "coletas"

    def __str__(self):
        return f"Coleta#{self.pk} {self.fonte.nome} [{self.estado}]"


class RegistroNormalizado(models.Model):
    fonte = models.ForeignKey(
        Fonte, on_delete=models.CASCADE, related_name="registros", verbose_name="fonte"
    )
    coleta = models.ForeignKey(
        Coleta,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros",
        verbose_name="coleta",
    )
    chave_externa = models.CharField(max_length=200, verbose_name="chave externa")
    dados = models.JSONField(default=dict, verbose_name="dados")
    coletado_em = models.DateTimeField(verbose_name="coletado em")
    usado_em = models.DateTimeField(null=True, blank=True, verbose_name="usado em")

    class Meta:
        ordering = ["-coletado_em"]
        verbose_name = "registro normalizado"
        verbose_name_plural = "registros normalizados"
        constraints = [
            models.UniqueConstraint(
                fields=["fonte", "chave_externa"], name="uniq_registro_fonte_chave"
            )
        ]

    def __str__(self):
        return f"{self.fonte.tipo}:{self.chave_externa}"


class Candidato(models.Model):
    registro = models.OneToOneField(
        RegistroNormalizado,
        on_delete=models.CASCADE,
        related_name="candidato",
        verbose_name="registro",
    )
    pontuacao = models.FloatField(default=0, verbose_name="pontuação")
    motivo = models.TextField(blank=True, default="", verbose_name="motivo")
    selecionado = models.BooleanField(default=True, verbose_name="selecionado")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        ordering = ["-pontuacao"]
        verbose_name = "candidato"
        verbose_name_plural = "candidatos"

    def __str__(self):
        return f"Candidato({self.registro.chave_externa}) score={self.pontuacao}"
