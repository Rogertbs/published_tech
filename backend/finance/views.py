from django.http import HttpResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from config.api import autorizado, json_response
from finance.reports import exportar_csv, resumo


def _filtros(request) -> dict:
    params = request.GET
    filtros = {}
    for campo, parser in (("inicio", parse_datetime), ("fim", parse_datetime)):
        valor = params.get(campo)
        if valor:
            filtros[campo] = parser(valor)
    for campo in ("provedor", "modelo", "finalidade", "etapa", "status"):
        if params.get(campo):
            filtros[campo] = params[campo]
    for campo in ("conteudo_id", "tarefa_id", "tentativa"):
        if params.get(campo):
            filtros[campo] = int(params[campo])
    return filtros


@require_GET
def custos(request):
    if not autorizado(request):
        return json_response({"detail": "Não autorizado."}, status=401)
    dados = resumo(_filtros(request))
    dados["total"] = str(dados["total"])
    return json_response(dados)


@require_GET
def custos_csv(request):
    if not autorizado(request):
        return json_response({"detail": "Não autorizado."}, status=401)
    conteudo = exportar_csv(_filtros(request))
    response = HttpResponse(conteudo, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="custos.csv"'
    return response
