from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from finance.services import exportar_csv, resumo


def _autorizado(request) -> bool:
    token = getattr(settings, "INTERNAL_API_TOKEN", None)
    if not token:
        return True
    return request.headers.get("X-Internal-Token") == token


def _filtros(request) -> dict:
    params = request.GET
    filtros = {}
    for campo, parser in (("inicio", parse_datetime), ("fim", parse_datetime)):
        valor = params.get(campo)
        if valor:
            filtros[campo] = parser(valor)
    for campo in ("provedor", "modelo", "finalidade", "status"):
        if params.get(campo):
            filtros[campo] = params[campo]
    for campo in ("conteudo_id", "tarefa_id", "tentativa"):
        if params.get(campo):
            filtros[campo] = int(params[campo])
    return filtros


def _json(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


@require_GET
def custos(request):
    if not _autorizado(request):
        return _json({"detail": "Não autorizado."}, status=401)
    dados = resumo(_filtros(request))
    dados["total"] = str(dados["total"])
    return _json(dados)


@require_GET
def custos_csv(request):
    if not _autorizado(request):
        return _json({"detail": "Não autorizado."}, status=401)
    conteudo = exportar_csv(_filtros(request))
    response = HttpResponse(conteudo, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="custos.csv"'
    return response
