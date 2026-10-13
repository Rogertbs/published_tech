import json

from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from config.api import autorizado, json_response
from pipeline import services as pipeline_services
from sources.models import Fonte


@csrf_exempt
@require_POST
def noticias(request):
    if not autorizado(request):
        return json_response({"detail": "Não autorizado."}, status=401)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return json_response({"detail": "JSON inválido."}, status=400)

    chave = body.get("chave_idempotencia")
    if chave and not cache.add(f"noticia:{chave}", 1, timeout=300):
        return json_response({"detail": "Já existe uma produção em andamento para esta chave."}, status=409)

    fonte = None
    if body.get("fonte_id"):
        fonte = Fonte.objects.filter(pk=body["fonte_id"]).first()

    try:
        resultado = pipeline_services.produzir_noticia(fonte=fonte)
    except pipeline_services.SemFonteRSS as exc:
        return json_response({"detail": str(exc)}, status=400)

    status = 201 if resultado.get("conteudo") else 502
    return json_response(resultado, status=status)
