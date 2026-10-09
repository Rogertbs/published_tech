from django.conf import settings
from django.db import models


class AuditoriaAdministrativa(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    acao = models.CharField(max_length=64)
    entidade = models.CharField(max_length=64)
    entidade_id = models.CharField(max_length=64)
    antes = models.JSONField(null=True, blank=True)
    depois = models.JSONField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Auditoria administrativa"
        verbose_name_plural = "Auditoria administrativa"

    def __str__(self):
        return f"{self.acao} {self.entidade}#{self.entidade_id}"
