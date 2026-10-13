import json

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from config.api import autorizado, json_response
from jobs import services as jobs
from pipeline.services import SECOES_CURADORIA


def _enfileirar(request, tipo, parametros):
    if not autorizado(request):
        return json_response({"detail": "Não autorizado."}, status=401)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return json_response({"detail": "JSON inválido."}, status=400)
    if body.get("fonte_id"):
        parametros["fonte_id"] = body["fonte_id"]
    try:
        tarefa, created = jobs.executar_agora(tipo, parametros, body.get("chave_idempotencia"))
    except jobs.MotorPausado:
        return json_response({"detail": "Motor pausado: não é possível executar."}, status=409)
    return json_response({"criada": created, **tarefa.as_dict()}, status=202 if created else 200)


@csrf_exempt
@require_POST
def noticias(request):
    return _enfileirar(request, "noticia", {})


@csrf_exempt
@require_POST
def curadorias(request):
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return json_response({"detail": "JSON inválido."}, status=400)
    secao = body.get("secao")
    if secao not in SECOES_CURADORIA:
        return json_response(
            {"detail": f"Informe 'secao' como uma de: {', '.join(SECOES_CURADORIA)}."}, status=400
        )
    return _enfileirar(request, "curadoria", {"secao": secao})
