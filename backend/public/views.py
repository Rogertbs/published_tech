from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from content.models import Conteudo, Secao, Versao
from content.services import HOME_KEY, artigo_key, secao_key


def _resumo_item(conteudo: Conteudo) -> dict:
    versao = conteudo.versao_publicada
    return {
        "slug": conteudo.slug,
        "secao": conteudo.secao,
        "tipo": conteudo.tipo,
        "titulo": versao.titulo,
        "resumo": versao.resumo,
        "publicado_em": conteudo.publicado_em.isoformat() if conteudo.publicado_em else None,
    }


def _item_completo(conteudo: Conteudo) -> dict:
    data = _resumo_item(conteudo)
    data["corpo"] = conteudo.versao_publicada.corpo
    return data


def _publicados():
    return Conteudo.objects.filter(versao_publicada__isnull=False).select_related("versao_publicada")


def _json(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def home(request):
    """Home page data; generated once and cached without TTL (render-once-and-cache)."""
    data = cache.get(HOME_KEY)
    if data is None:
        lista = [_resumo_item(c) for c in _publicados().order_by("-publicado_em")]
        data = {
            "artigos": [i for i in lista if i["secao"] == Secao.ARTIGOS],
            "destaques_github": [i for i in lista if i["secao"] == Secao.DESTAQUES_GITHUB],
            "radar_hf": [i for i in lista if i["secao"] == Secao.RADAR_HF],
        }
        cache.set(HOME_KEY, data, timeout=None)
    return _json(data)


def secao(request, secao):
    if secao not in Secao.values:
        return _json({"detail": "Seção não encontrada."}, status=404)
    key = secao_key(secao)
    data = cache.get(key)
    if data is None:
        itens = [_resumo_item(c) for c in _publicados().filter(secao=secao).order_by("-publicado_em")]
        data = {"secao": secao, "itens": itens}
        cache.set(key, data, timeout=None)
    return _json(data)


def artigo(request, slug):
    key = artigo_key(slug)
    data = cache.get(key)
    if data is None:
        conteudo = get_object_or_404(_publicados(), slug=slug)
        data = _item_completo(conteudo)
        cache.set(key, data, timeout=None)
    return _json(data)
