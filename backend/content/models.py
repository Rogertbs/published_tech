from django.conf import settings
from django.db import models


class Secao(models.TextChoices):
    ARTIGOS = "artigos", "Artigos"
    NOTICIAS = "noticias", "Notícias"
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
    slug = models.SlugField(max_length=200, unique=True, verbose_name="slug")
    secao = models.CharField(max_length=32, choices=Secao.choices, verbose_name="seção")
    tipo = models.CharField(
        max_length=16, choices=TipoConteudo.choices, default=TipoConteudo.ARTIGO, verbose_name="tipo"
    )
    estado = models.CharField(
        max_length=24,
        choices=EstadoConteudo.choices,
        default=EstadoConteudo.RASCUNHO,
        verbose_name="estado",
    )
    versao_publicada = models.ForeignKey(
        "Versao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="publicado_em_conteudos",
        verbose_name="versão publicada",
    )
    versao_em_edicao = models.ForeignKey(
        "Versao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="em_edicao_em_conteudos",
        verbose_name="versão em edição",
    )
    publicado_em = models.DateTimeField(null=True, blank=True, verbose_name="publicado em")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="atualizado em")

    class Meta:
        ordering = ["-publicado_em", "-criado_em"]
        verbose_name = "conteúdo"
        verbose_name_plural = "conteúdos"

    def __str__(self):
        return self.slug

    @property
    def esta_publicado(self) -> bool:
        return self.versao_publicada_id is not None


class Versao(models.Model):
    conteudo = models.ForeignKey(
        Conteudo, on_delete=models.CASCADE, related_name="versoes", verbose_name="conteúdo"
    )
    titulo = models.CharField(max_length=300, verbose_name="título")
    resumo = models.TextField(blank=True, default="", verbose_name="resumo")
    corpo = models.TextField(blank=True, default="", verbose_name="corpo")
    hash_origem = models.CharField(
        max_length=64, blank=True, default="", db_index=True, verbose_name="hash da origem"
    )
    metadados = models.JSONField(default=dict, blank=True, verbose_name="metadados")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "versão"
        verbose_name_plural = "versões"

    def __str__(self):
        return f"{self.conteudo.slug} v{self.pk}"

    @property
    def aprovada(self) -> bool:
        return hasattr(self, "aprovacao")


class Item(models.Model):
    class TipoItem(models.TextChoices):
        REPOSITORIO = "repositorio", "Repositório"
        MODELO = "modelo", "Modelo"

    versao = models.ForeignKey(
        Versao, on_delete=models.CASCADE, related_name="itens", verbose_name="versão"
    )
    ordem = models.PositiveIntegerField(verbose_name="ordem")
    tipo = models.CharField(
        max_length=16, choices=TipoItem.choices, default=TipoItem.REPOSITORIO, verbose_name="tipo"
    )
    dados = models.JSONField(default=dict, verbose_name="dados")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        ordering = ["ordem"]
        verbose_name = "item"
        verbose_name_plural = "itens"
        constraints = [
            models.UniqueConstraint(fields=["versao", "ordem"], name="uniq_item_versao_ordem")
        ]

    def __str__(self):
        return f"Item#{self.ordem} de {self.versao}"


class Aprovacao(models.Model):
    class Origem(models.TextChoices):
        HUMANO = "humano", "Humano"
        AUTOMATICO = "automatico", "Automático"

    versao = models.OneToOneField(
        Versao, on_delete=models.CASCADE, related_name="aprovacao", verbose_name="versão"
    )
    origem = models.CharField(
        max_length=16, choices=Origem.choices, default=Origem.HUMANO, verbose_name="origem"
    )
    aprovador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="aprovador",
    )
    regras_avaliadas = models.JSONField(
        default=list, blank=True, verbose_name="regras avaliadas"
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        verbose_name = "aprovação"
        verbose_name_plural = "aprovações"

    def __str__(self):
        return f"aprovação de {self.versao}"


class Publicacao(models.Model):
    conteudo = models.ForeignKey(
        Conteudo, on_delete=models.CASCADE, related_name="publicacoes", verbose_name="conteúdo"
    )
    versao = models.ForeignKey(
        Versao, on_delete=models.PROTECT, related_name="publicacoes", verbose_name="versão"
    )
    publicado_em = models.DateTimeField(verbose_name="publicado em")
    retirado_em = models.DateTimeField(null=True, blank=True, verbose_name="retirado em")

    class Meta:
        ordering = ["-publicado_em"]
        verbose_name = "publicação"
        verbose_name_plural = "publicações"
        constraints = [
            models.UniqueConstraint(
                fields=["conteudo", "versao"],
                condition=models.Q(retirado_em__isnull=True),
                name="uniq_publicacao_ativa_conteudo_versao",
            )
        ]

    def __str__(self):
        return f"publicação de {self.conteudo.slug} ({self.publicado_em:%Y-%m-%d})"

    @property
    def ativa(self) -> bool:
        return self.retirado_em is None
