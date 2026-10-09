import time

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from content.models import Conteudo, Secao, TipoConteudo
from content.services import HOME_KEY, artigo_key, item_key, secao_key


def _resumo_item(conteudo: Conteudo) -> dict:
    versao = conteudo.versao_publicada
    return {
        "slug": conteudo.slug,
        "secao": conteudo.secao,
        "tipo": conteudo.tipo,
        "titulo": versao.titulo,
        "resumo": versao.resumo,
        "itens_count": versao.itens.count() if conteudo.tipo == TipoConteudo.LISTA else 0,
        "publicado_em": conteudo.publicado_em.isoformat() if conteudo.publicado_em else None,
    }


def _item_completo(conteudo: Conteudo) -> dict:
    data = _resumo_item(conteudo)
    versao = conteudo.versao_publicada
    data["corpo"] = versao.corpo
    if conteudo.tipo == TipoConteudo.LISTA:
        data["aviso_curadoria"] = versao.metadados.get("aviso_curadoria", "")
        data["itens"] = [
            {"ordem": item.ordem, "tipo": item.tipo, "dados": item.dados}
            for item in versao.itens.all()
        ]
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

    return _json(_cached(HOME_KEY, build))


def secao(request, secao):
    if secao not in Secao.values:
        return _json({"detail": "Seção não encontrada."}, status=404)

    def build():
        itens = [_resumo_item(c) for c in _publicados().filter(secao=secao).order_by("-publicado_em")]
        return {"secao": secao, "itens": itens}

    return _json(_cached(secao_key(secao), build))


def artigo(request, slug):
    def build():
        return _item_completo(get_object_or_404(_publicados(), slug=slug))

    return _json(_cached(artigo_key(slug), build))


def item(request, slug, ordem):
    def build():
        conteudo = get_object_or_404(_publicados(), slug=slug)
        versao = conteudo.versao_publicada
        registro = versao.itens.filter(ordem=ordem).first()
        if registro is None:
            return None
        return {
            "conteudo": conteudo.slug,
            "secao": conteudo.secao,
            "titulo": versao.titulo,
            "aviso_curadoria": versao.metadados.get("aviso_curadoria", ""),
            "ordem": registro.ordem,
            "tipo": registro.tipo,
            "dados": registro.dados,
        }

    data = _cached(item_key(slug, ordem), build)
    if data is None:
        return _json({"detail": "Item não encontrado."}, status=404)
    return _json(data)
