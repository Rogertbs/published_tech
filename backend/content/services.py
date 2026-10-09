import logging

import redis
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from auditoria import services as auditoria
from content.models import Aprovacao, Conteudo, EstadoConteudo, Item, Publicacao, Versao

logger = logging.getLogger(__name__)

HOME_KEY = "public:home"
PAGE_KEY_PREFIX = "pt:page:"


def secao_key(secao: str) -> str:
    return f"public:secao:{secao}"


def artigo_key(slug: str) -> str:
    return f"public:artigo:{slug}"


def item_key(slug: str, ordem: int) -> str:
    return f"public:item:{slug}:{ordem}"


def _page_cache_keys(conteudo: Conteudo) -> list[str]:
    chaves = [
        f"{PAGE_KEY_PREFIX}/",
        f"{PAGE_KEY_PREFIX}/secao/{conteudo.secao}",
        f"{PAGE_KEY_PREFIX}/artigo/{conteudo.slug}",
    ]
    for ordem in range(1, 6):
        chaves.append(f"{PAGE_KEY_PREFIX}/artigo/{conteudo.slug}/item/{ordem}")
    chaves.append(f"{PAGE_KEY_PREFIX}/sitemap.xml")
    return chaves


def invalidar_publico(conteudo: Conteudo) -> None:
    try:
        cache.delete(HOME_KEY)
        cache.delete(secao_key(conteudo.secao))
        cache.delete(artigo_key(conteudo.slug))
        for ordem in range(1, 6):
            cache.delete(item_key(conteudo.slug, ordem))
    except Exception:
        logger.warning("Não foi possível invalidar o cache da API.", exc_info=True)

    redis_url = getattr(settings, "REDIS_URL", None)
    if not redis_url:
        return
    try:
        client = redis.Redis.from_url(redis_url)
        client.delete(*_page_cache_keys(conteudo))
    except Exception:
        logger.warning("Não foi possível invalidar o cache de páginas no Redis.", exc_info=True)


def _lock_conteudo(conteudo: Conteudo) -> Conteudo:
    qs = Conteudo.objects.filter(pk=conteudo.pk)
    if connection.vendor == "postgresql":
        qs = qs.select_for_update()
    return qs.get()


def versao_publicavel(conteudo: Conteudo) -> Versao | None:
    versao = conteudo.versao_em_edicao
    if versao is not None and hasattr(versao, "aprovacao"):
        return versao
    return None


@transaction.atomic
def aprovar(
    versao: Versao,
    aprovador=None,
    origem: str = Aprovacao.Origem.HUMANO,
    regras_avaliadas=None,
) -> Aprovacao:
    aprovacao, _ = Aprovacao.objects.get_or_create(
        versao=versao,
        defaults={
            "aprovador": aprovador,
            "origem": origem,
            "regras_avaliadas": regras_avaliadas or [],
        },
    )
    conteudo = _lock_conteudo(versao.conteudo)
    conteudo.estado = (
        EstadoConteudo.PUBLICADO_EM_EDICAO if conteudo.esta_publicado else EstadoConteudo.APROVADO
    )
    conteudo.save(update_fields=["estado", "atualizado_em"])
    auditoria.registrar(
        "aprovar",
        "Conteudo",
        conteudo.pk,
        usuario=aprovador,
        depois={"versao": versao.pk, "origem": origem, "regras_avaliadas": aprovacao.regras_avaliadas},
    )
    return aprovacao


@transaction.atomic
def editar(conteudo: Conteudo, *, titulo, resumo="", corpo="", usuario=None, itens=None) -> Versao:
    conteudo = _lock_conteudo(conteudo)
    versao = Versao.objects.create(
        conteudo=conteudo, titulo=titulo, resumo=resumo, corpo=corpo
    )
    for ordem, item in enumerate(itens or [], start=1):
        Item.objects.create(
            versao=versao,
            ordem=ordem,
            tipo=item.get("tipo", Item.TipoItem.REPOSITORIO),
            dados=item.get("dados", {}),
        )
    conteudo.versao_em_edicao = versao
    conteudo.estado = (
        EstadoConteudo.PUBLICADO_EM_EDICAO if conteudo.esta_publicado else EstadoConteudo.RASCUNHO
    )
    conteudo.save(update_fields=["versao_em_edicao", "estado", "atualizado_em"])
    auditoria.registrar(
        "editar", "Conteudo", conteudo.pk, usuario=usuario, depois={"versao": versao.pk}
    )
    transaction.on_commit(lambda: invalidar_publico(conteudo))
    return versao


@transaction.atomic
def publicar(conteudo: Conteudo, versao: Versao, quando=None) -> Publicacao:
    if versao.conteudo_id != conteudo.pk:
        raise ValueError("A versão não pertence a este conteúdo.")
    if not hasattr(versao, "aprovacao"):
        raise ValueError("Somente uma versão aprovada pode ser publicada.")

    conteudo = _lock_conteudo(conteudo)
    if conteudo.versao_em_edicao_id and versao.pk != conteudo.versao_em_edicao_id:
        raise ValueError("A versão informada não é a versão em edição aprovada.")

    quando = quando or timezone.now()
    ativa = Publicacao.objects.select_for_update().filter(
        conteudo=conteudo, retirado_em__isnull=True
    ).first()
    if ativa is not None and ativa.versao_id == versao.pk:
        publicacao = ativa
    else:
        if ativa is not None:
            ativa.retirado_em = quando
            ativa.save(update_fields=["retirado_em"])
        try:
            publicacao = Publicacao.objects.create(
                conteudo=conteudo, versao=versao, publicado_em=quando
            )
        except IntegrityError:
            publicacao = Publicacao.objects.get(
                conteudo=conteudo, versao=versao, retirado_em__isnull=True
            )

    conteudo.versao_publicada = versao
    conteudo.versao_em_edicao = None
    conteudo.publicado_em = quando
    conteudo.estado = EstadoConteudo.PUBLICADO
    conteudo.save(
        update_fields=[
            "versao_publicada",
            "versao_em_edicao",
            "publicado_em",
            "estado",
            "atualizado_em",
        ]
    )

    auditoria.registrar(
        "publicar",
        "Conteudo",
        conteudo.pk,
        depois={"versao": versao.pk, "publicacao": publicacao.pk},
    )
    transaction.on_commit(lambda: invalidar_publico(conteudo))
    return publicacao


@transaction.atomic
def retirar(conteudo: Conteudo, quando=None) -> None:
    conteudo = _lock_conteudo(conteudo)
    quando = quando or timezone.now()
    Publicacao.objects.filter(conteudo=conteudo, retirado_em__isnull=True).update(retirado_em=quando)
    conteudo.versao_publicada = None
    conteudo.versao_em_edicao = None
    conteudo.publicado_em = None
    conteudo.estado = EstadoConteudo.RETIRADO
    conteudo.save(
        update_fields=[
            "versao_publicada",
            "versao_em_edicao",
            "publicado_em",
            "estado",
            "atualizado_em",
        ]
    )

    auditoria.registrar("retirar", "Conteudo", conteudo.pk)
    transaction.on_commit(lambda: invalidar_publico(conteudo))
