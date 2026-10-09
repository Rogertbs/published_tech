import csv
import io
from decimal import Decimal

from django.db.models import Sum

from ai.models import ChamadaIA
from finance.services import ZERO, tz_local


def _filtrar(filtros: dict):
    qs = ChamadaIA.objects.all()
    if filtros.get("inicio"):
        qs = qs.filter(iniciada_em__gte=filtros["inicio"])
    if filtros.get("fim"):
        qs = qs.filter(iniciada_em__lt=filtros["fim"])
    for campo in ("provedor", "modelo", "finalidade", "etapa", "status"):
        if filtros.get(campo) is not None:
            qs = qs.filter(**{campo: filtros[campo]})
    for campo in ("conteudo_id", "tarefa_id", "tentativa"):
        if filtros.get(campo) is not None:
            qs = qs.filter(**{campo: filtros[campo]})
    return qs


def _somar(qs, campo) -> dict:
    return {
        linha[campo] or "": linha["total"] or ZERO
        for linha in qs.values(campo).annotate(total=Sum("custo"))
    }


def resumo(filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    qs = _filtrar(filtros)
    total = qs.aggregate(total=Sum("custo")).get("total") or ZERO
    por_dia = {}
    for chamada in qs.filter(custo__isnull=False):
        dia = chamada.iniciada_em.astimezone(tz_local()).date().isoformat()
        por_dia[dia] = por_dia.get(dia, ZERO) + chamada.custo
    return {
        "total": total,
        "quantidade": qs.count(),
        "por_provedor": _somar(qs, "provedor"),
        "por_modelo": _somar(qs, "modelo"),
        "por_finalidade": _somar(qs, "finalidade"),
        "por_etapa": _somar(qs, "etapa"),
        "por_tarefa": {str(k): v for k, v in _somar(qs, "tarefa_id").items()},
        "por_execucao": {str(k): v for k, v in _somar(qs, "execucao_id").items()},
        "por_conteudo": {str(k): v for k, v in _somar(qs, "conteudo_id").items()},
        "por_dia": por_dia,
    }


def _colunas():
    return [
        ("id", lambda c: c.pk),
        ("iniciada_em", lambda c: c.iniciada_em.astimezone(tz_local()).isoformat()),
        ("provedor", lambda c: c.provedor),
        ("modelo", lambda c: c.modelo),
        ("finalidade", lambda c: c.finalidade),
        ("etapa", lambda c: c.etapa),
        ("status", lambda c: c.status),
        ("tentativa", lambda c: c.tentativa),
        ("duracao_ms", lambda c: c.duracao_ms),
        ("request_id_externo", lambda c: c.request_id_externo),
        ("tokens_entrada", lambda c: c.tokens_entrada),
        ("tokens_saida", lambda c: c.tokens_saida),
        ("tokens_cache", lambda c: c.tokens_cache),
        ("moeda", lambda c: c.moeda),
        ("preco_aplicado", lambda c: "" if c.preco_aplicado is None else str(c.preco_aplicado)),
        ("custo", lambda c: "" if c.custo is None else str(c.custo)),
        ("origem_custo", lambda c: c.origem_custo),
        ("tarefa_id", lambda c: c.tarefa_id),
        ("conteudo_id", lambda c: c.conteudo_id),
    ]


def exportar_csv(filtros: dict | None = None) -> str:
    filtros = filtros or {}
    colunas = _colunas()
    buff = io.StringIO()
    escritor = csv.writer(buff)
    escritor.writerow([nome for nome, _ in colunas])
    for chamada in _filtrar(filtros).order_by("iniciada_em"):
        escritor.writerow([getter(chamada) for _, getter in colunas])
    return buff.getvalue()
