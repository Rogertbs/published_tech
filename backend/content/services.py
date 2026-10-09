import logging

import redis
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from content.models import Aprovacao, Conteudo, Publicacao, Versao

logger = logging.getLogger(__name__)

HOME_KEY = "public:home"


def secao_key(secao: str) -> str:
    return f"public:secao:{secao}"


def artigo_key(slug: str) -> str:
    return f"public:artigo:{slug}"


def _page_cache_keys(conteudo: Conteudo) -> list[str]:
    # Keys used by the frontend (Astro) page cache, shared via Redis.
    return [
        "pt:page:/",
        f"pt:page:/secao/{conteudo.secao}",
        f"pt:page:/artigo/{conteudo.slug}",
    ]


def invalidar_publico(conteudo: Conteudo) -> None:
    """Invalidate public caches after a commit.

    Clears the Django API cache (render-once-and-cache) and, best-effort, the
    frontend page cache keys sharing the same Redis.
    """
    cache.delete(HOME_KEY)
    cache.delete(secao_key(conteudo.secao))
    cache.delete(artigo_key(conteudo.slug))

    redis_url = getattr(settings, "REDIS_URL", None)
    if not redis_url:
        return
    try:
        client = redis.Redis.from_url(redis_url)
        client.delete(*_page_cache_keys(conteudo))
    except Exception:  # pragma: no cover - Redis is optional in dev/tests
        logger.warning("Não foi possível invalidar o cache de páginas no Redis.", exc_info=True)


def aprovar(versao: Versao, aprovador=None, origem: str = Aprovacao.Origem.HUMANO) -> Aprovacao:
    aprovacao, _ = Aprovacao.objects.get_or_create(
        versao=versao,
        defaults={"aprovador": aprovador, "origem": origem, "regras_avaliadas": []},
    )
    return aprovacao


def publicar(conteudo: Conteudo, versao: Versao, quando=None) -> Publicacao:
    if versao.conteudo_id != conteudo.pk:
        raise ValueError("A versão não pertence a este conteúdo.")
    if not hasattr(versao, "aprovacao"):
        raise ValueError("Somente uma versão aprovada pode ser publicada.")

    quando = quando or timezone.now()
    publicacao = Publicacao.objects.create(
        conteudo=conteudo, versao=versao, publicado_em=quando
    )
    conteudo.versao_publicada = versao
    conteudo.versao_em_edicao = None
    conteudo.publicado_em = quando
    conteudo.save(update_fields=["versao_publicada", "versao_em_edicao", "publicado_em", "atualizado_em"])

    invalidar_publico(conteudo)
    return publicacao


def retirar(conteudo: Conteudo, quando=None) -> None:
    quando = quando or timezone.now()
    Publicacao.objects.filter(conteudo=conteudo, retirado_em__isnull=True).update(retirado_em=quando)
    conteudo.versao_publicada = None
    conteudo.publicado_em = None
    conteudo.save(update_fields=["versao_publicada", "publicado_em", "atualizado_em"])

    invalidar_publico(conteudo)
