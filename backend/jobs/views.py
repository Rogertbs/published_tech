import json

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from config.api import autorizado, json_response
from jobs import services
from jobs.models import Tarefa


@csrf_exempt
@require_POST
def execucoes(request):
    if not autorizado(request):
        return json_response({"detail": "Não autorizado."}, status=401)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return json_response({"detail": "JSON inválido."}, status=400)

    tipo = body.get("tipo")
    if not tipo:
        return json_response({"detail": "O campo 'tipo' é obrigatório."}, status=400)

    try:
        tarefa, created = services.executar_agora(
            tipo, body.get("parametros"), body.get("chave_idempotencia")
        )
    except services.MotorPausado:
        return json_response({"detail": "Motor pausado: não é possível executar."}, status=409)

    return json_response({"criada": created, **tarefa.as_dict()}, status=202 if created else 200)


@require_GET
def execucao(request, pk):
    if not autorizado(request):
        return json_response({"detail": "Não autorizado."}, status=401)
    try:
        tarefa = Tarefa.objects.get(pk=pk)
    except Tarefa.DoesNotExist:
        return json_response({"detail": "Execução não encontrada."}, status=404)
    return json_response(tarefa.as_dict())
