import hashlib

from django.core.management.base import BaseCommand
from django.utils import timezone

from content.models import Versao
from pipeline.models import Evidencia
from sources.models import RegistroNormalizado


def _chaves_da_versao(versao: Versao) -> list[str]:
    pares = Evidencia.objects.filter(versao=versao, registro__isnull=False).values_list(
        "registro__fonte__tipo", "registro__chave_externa"
    )
    return [f"{tipo}:{chave}" for tipo, chave in pares if chave]


def hash_da_versao(versao: Versao) -> str:
    chaves = _chaves_da_versao(versao)
    if not chaves:
        return ""
    return hashlib.sha256("\n".join(sorted(chaves)).encode("utf-8")).hexdigest()


class Command(BaseCommand):
    help = (
        "Preenche hash_origem das versões e marca a origem (usado_em) dos registros "
        "usados em conteúdo, para cobrir conteúdo anterior à deduplicação."
    )

    def handle(self, *args, **options):
        hashes = 0
        for versao in Versao.objects.filter(hash_origem="").order_by("pk"):
            assinatura = hash_da_versao(versao)
            if assinatura:
                versao.hash_origem = assinatura
                versao.save(update_fields=["hash_origem"])
                hashes += 1

        registros = (
            Evidencia.objects.filter(versao__isnull=False, registro__isnull=False)
            .values_list("registro_id", flat=True)
            .distinct()
        )
        marcados = RegistroNormalizado.objects.filter(
            pk__in=list(registros), usado_em__isnull=True
        ).update(usado_em=timezone.now())

        self.stdout.write(
            self.style.SUCCESS(
                f"hashes preenchidos: {hashes}; registros marcados como usados: {marcados}"
            )
        )
