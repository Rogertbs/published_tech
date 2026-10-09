from django.conf import settings
from django.db import models


class Secao(models.TextChoices):
    ARTIGOS = "artigos", "Artigos"
    DESTAQUES_GITHUB = "destaques-github", "Destaques GitHub"
    RADAR_HF = "radar-hf", "Radar Hugging Face"


class TipoConteudo(models.TextChoices):
    ARTIGO = "artigo", "Artigo"
    LISTA = "lista", "Lista (curadoria)"


class EstadoConteudo(models.TextChoices):
    RASCUNHO = "rascunho", "Rascunho"
    AGUARDANDO_REVISAO = "aguardando_revisao", "Aguardando revisão"
    APROVADO = "aprovado", "Aprovado"
    PUBLICADO = "publicado", "Publicado"
    PUBLICADO_EM_EDICAO = "publicado_em_edicao", "Publicado em edição"
    REJEITADO = "rejeitado", "Rejeitado"
    RETIRADO = "retirado", "Retirado"


class Conteudo(models.Model):
    slug = models.SlugField(max_length=200, unique=True)
    secao = models.CharField(max_length=32, choices=Secao.choices)
    tipo = models.CharField(max_length=16, choices=TipoConteudo.choices, default=TipoConteudo.ARTIGO)
    estado = models.CharField(
        max_length=24, choices=EstadoConteudo.choices, default=EstadoConteudo.RASCUNHO
    )
    versao_publicada = models.ForeignKey(
        "Versao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="publicado_em_conteudos",
    )
    versao_em_edicao = models.ForeignKey(
        "Versao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="em_edicao_em_conteudos",
    )
    publicado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-publicado_em", "-criado_em"]

    def __str__(self):
        return self.slug

    @property
    def esta_publicado(self) -> bool:
        return self.versao_publicada_id is not None


class Versao(models.Model):
    conteudo = models.ForeignKey(Conteudo, on_delete=models.CASCADE, related_name="versoes")
    titulo = models.CharField(max_length=300)
    resumo = models.TextField(blank=True, default="")
    corpo = models.TextField(blank=True, default="")
    metadados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.conteudo.slug} v{self.pk}"

    @property
    def aprovada(self) -> bool:
        return hasattr(self, "aprovacao")


class Aprovacao(models.Model):
    class Origem(models.TextChoices):
        HUMANO = "humano", "Humano"
        AUTOMATICO = "automatico", "Automático"

    versao = models.OneToOneField(Versao, on_delete=models.CASCADE, related_name="aprovacao")
    origem = models.CharField(max_length=16, choices=Origem.choices, default=Origem.HUMANO)
    aprovador = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    regras_avaliadas = models.JSONField(default=list, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"aprovação de {self.versao}"


class Publicacao(models.Model):
    conteudo = models.ForeignKey(Conteudo, on_delete=models.CASCADE, related_name="publicacoes")
    versao = models.ForeignKey(Versao, on_delete=models.PROTECT, related_name="publicacoes")
    publicado_em = models.DateTimeField()
    retirado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-publicado_em"]

    def __str__(self):
        return f"publicação de {self.conteudo.slug} ({self.publicado_em:%Y-%m-%d})"

    @property
    def ativa(self) -> bool:
        return self.retirado_em is None
