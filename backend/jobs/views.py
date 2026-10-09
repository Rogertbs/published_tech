import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from jobs import services
from jobs.models import Tarefa


def _json(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def _resumo(tarefa: Tarefa) -> dict:
    return {
        "id": tarefa.pk,
        "tipo": tarefa.tipo_tarefa,
        "estado": tarefa.estado,
        "origem": tarefa.origem,
        "tentativas": tarefa.tentativas,
        "resultado": tarefa.resultado,
        "erro": tarefa.erro,
    }


@csrf_exempt
@require_POST
def execucoes(request):
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return _json({"detail": "JSON inválido."}, status=400)

    tipo = body.get("tipo")
    if not tipo:
        return _json({"detail": "O campo 'tipo' é obrigatório."}, status=400)

    try:
        tarefa, created = services.executar_agora(
            tipo, body.get("parametros"), body.get("chave_idempotencia")
        )
    except services.MotorPausado:
        return _json({"detail": "Motor pausado: não é possível executar."}, status=409)

    return _json({"criada": created, **_resumo(tarefa)}, status=202 if created else 200)


@require_GET
def execucao(request, pk):
    try:
        tarefa = Tarefa.objects.get(pk=pk)
    except Tarefa.DoesNotExist:
        return _json({"detail": "Execução não encontrada."}, status=404)
    return _json(_resumo(tarefa))
