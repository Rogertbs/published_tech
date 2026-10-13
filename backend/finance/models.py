from decimal import Decimal

from django.conf import settings
from django.db import models


class EstadoReserva(models.TextChoices):
    ATIVA = "ativa", "Ativa"
    CONCILIADA = "conciliada", "Conciliada"
    EXPIRADA = "expirada", "Expirada"


class ConfiguracaoOrcamento(models.Model):
    limite_diario = models.DecimalField(
        max_digits=14, decimal_places=6, verbose_name="limite diário"
    )
    limite_mensal = models.DecimalField(
        max_digits=14, decimal_places=6, verbose_name="limite mensal"
    )
    moeda = models.CharField(max_length=8, default="USD", verbose_name="moeda")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="atualizado em")

    class Meta:
        verbose_name = "Configuração de orçamento"
        verbose_name_plural = "Configuração de orçamento"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "ConfiguracaoOrcamento":
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "limite_diario": Decimal(getattr(settings, "ORCAMENTO_DIARIO", "5")),
                "limite_mensal": Decimal(getattr(settings, "ORCAMENTO_MENSAL", "30")),
                "moeda": getattr(settings, "ORCAMENTO_MOEDA", "USD"),
            },
        )
        return obj

    def __str__(self):
        return "Orçamento"


class ReservaOrcamento(models.Model):
    provedor = models.CharField(max_length=64, blank=True, default="", verbose_name="provedor")
    modelo = models.CharField(max_length=200, blank=True, default="", verbose_name="modelo")
    valor_estimado = models.DecimalField(
        max_digits=14, decimal_places=6, verbose_name="valor estimado"
    )
    moeda = models.CharField(max_length=8, default="USD", verbose_name="moeda")
    estado = models.CharField(
        max_length=16, choices=EstadoReserva.choices, default=EstadoReserva.ATIVA, verbose_name="estado"
    )
    chamada = models.OneToOneField(
        "ai.ChamadaIA",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reserva",
        verbose_name="chamada",
    )
    criada_em = models.DateTimeField(auto_now_add=True, verbose_name="criada em")
    expira_em = models.DateTimeField(verbose_name="expira em")
    conciliada_em = models.DateTimeField(null=True, blank=True, verbose_name="conciliada em")

    class Meta:
        ordering = ["-criada_em"]
        verbose_name = "reserva de orçamento"
        verbose_name_plural = "reservas de orçamento"

    def __str__(self):
        return f"Reserva#{self.pk} {self.valor_estimado} [{self.estado}]"


class EventoOrcamento(models.Model):
    class Tipo(models.TextChoices):
        BLOQUEIO = "bloqueio", "Bloqueio"

    tipo = models.CharField(
        max_length=16, choices=Tipo.choices, default=Tipo.BLOQUEIO, verbose_name="tipo"
    )
    limite_atingido = models.CharField(
        max_length=16, blank=True, default="", verbose_name="limite atingido"
    )
    valor_solicitado = models.DecimalField(
        max_digits=14, decimal_places=6, verbose_name="valor solicitado"
    )
    gasto_dia = models.DecimalField(max_digits=14, decimal_places=6, verbose_name="gasto no dia")
    gasto_mes = models.DecimalField(max_digits=14, decimal_places=6, verbose_name="gasto no mês")
    detalhe = models.TextField(blank=True, default="", verbose_name="detalhe")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="criado em")

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "evento de orçamento"
        verbose_name_plural = "eventos de orçamento"

    def __str__(self):
        return f"EventoOrcamento[{self.tipo}] {self.limite_atingido}"
