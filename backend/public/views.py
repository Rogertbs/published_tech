import time

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from content.models import Conteudo, Secao


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


def _cached(key: str, builder):
    data = cache.get(key)
    if data is not None:
        return data

    lock_key = f"{key}:lock"
    if cache.add(lock_key, 1, timeout=10):
        try:
            data = builder()
            cache.set(key, data, timeout=None)
            return data
        finally:
            cache.delete(lock_key)

    for _ in range(20):
        time.sleep(0.05)
        data = cache.get(key)
        if data is not None:
            return data
    return builder()


def _json(payload, status=200):
    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def home(request):
    def build():
        lista = [_resumo_item(c) for c in _publicados().order_by("-publicado_em")]
        return {
            "artigos": [i for i in lista if i["secao"] == Secao.ARTIGOS],
            "destaques_github": [i for i in lista if i["secao"] == Secao.DESTAQUES_GITHUB],
            "radar_hf": [i for i in lista if i["secao"] == Secao.RADAR_HF],
        }

    return _json(_cached("public:home", build))


def secao(request, secao):
    if secao not in Secao.values:
        return _json({"detail": "Seção não encontrada."}, status=404)

    def build():
        itens = [_resumo_item(c) for c in _publicados().filter(secao=secao).order_by("-publicado_em")]
        return {"secao": secao, "itens": itens}

    return _json(_cached(f"public:secao:{secao}", build))


def artigo(request, slug):
    def build():
        return _item_completo(get_object_or_404(_publicados(), slug=slug))

    return _json(_cached(f"public:artigo:{slug}", build))
