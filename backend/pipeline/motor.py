from typing import TypedDict

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ai import instrumentation
from configuracao import services as configuracao
from content.models import Conteudo, EstadoConteudo, Item, Secao, TipoConteudo, Versao
from finance.services import OrcamentoExcedido
from pipeline.imagens import gerar_ilustracao
from pipeline.models import EstadoExecucao, EtapaExecucao, Evidencia, Execucao
from sources.models import Candidato, Fonte, TipoFonte

SECAO_TIPO = {
    Secao.DESTAQUES_GITHUB: TipoFonte.GITHUB,
    Secao.RADAR_HF: TipoFonte.HUGGINGFACE,
}
AVISO_CURADORIA = "Curadoria própria — não é ranking oficial de terceiros."
PROMPT_PADRAO = "Redija uma análise curta em português, prática, com base apenas nas evidências."


class EstadoPipeline(TypedDict, total=False):
    execucao_id: int
    secao: str
    candidatos: list
    evidencias: list
    afirmacoes: list
    fonte_resumo: str
    contradicao: bool
    texto: str
    redacao_status: str
    revisao: dict
    imagem: dict
    conteudo_id: int
    versao_id: int
    motivo: str


def _quantidade(secao: str) -> int:
    campos = configuracao.resolver(secao=secao)
    if "quantidade_itens" in campos:
        return max(1, min(int(campos["quantidade_itens"]), 5))
    tipo = SECAO_TIPO.get(secao)
    fonte = Fonte.objects.filter(tipo=tipo, habilitada=True).order_by("id").first() if tipo else None
    if fonte:
        return max(1, min(int(fonte.parametros.get("selecao", 1)), 5))
    return 1


def _selecionar_candidatos(secao: str) -> list[Candidato]:
    qs = (
        Candidato.objects.filter(selecionado=True)
        .select_related("registro", "registro__fonte")
        .order_by("-pontuacao")
    )
    tipo = SECAO_TIPO.get(secao)
    if tipo:
        qs = qs.filter(registro__fonte__tipo=tipo)
    return list(qs[: _quantidade(secao)])


def _resumo_registro(dados: dict) -> str:
    nome = dados.get("full_name") or dados.get("id") or ""
    descricao = dados.get("description") or dados.get("resumo") or ""
    return f"{nome}: {descricao}".strip()


def etapa(nome):
    def decorator(fn):
        def wrapper(state: EstadoPipeline) -> dict:
            execucao = Execucao.objects.get(pk=state["execucao_id"])
            with transaction.atomic():
                qs = EtapaExecucao.objects.filter(execucao=execucao, nome=nome)
                if connection.vendor == "postgresql":
                    qs = qs.select_for_update()
                existente = qs.first()
                if existente is not None:
                    return existente.saida
                saida = fn(execucao, state)
                try:
                    EtapaExecucao.objects.create(execucao=execucao, nome=nome, saida=saida)
                except IntegrityError:
                    return EtapaExecucao.objects.get(execucao=execucao, nome=nome).saida
                return saida

        return wrapper

    return decorator


@etapa("selecionar")
def no_selecionar(execucao, state):
    candidatos = _selecionar_candidatos(state["secao"])
    return {"candidatos": [c.pk for c in candidatos]}


@etapa("evidencias")
def no_evidencias(execucao, state):
    evidencias, afirmacoes, resumos, chaves, contradicao = [], [], [], {}, False
    for candidato in Candidato.objects.filter(pk__in=state.get("candidatos", [])).select_related(
        "registro", "registro__fonte"
    ):
        registro = candidato.registro
        dados = registro.dados
        url = dados.get("html_url") or dados.get("url") or ""
        trecho = dados.get("description") or dados.get("resumo") or ""
        evidencia_ids = []
        if url or trecho:
            evidencia = Evidencia.objects.create(
                execucao=execucao,
                fonte=registro.fonte,
                registro=registro,
                tipo=registro.fonte.tipo,
                url=url,
                trecho=trecho,
                coletado_em=registro.coletado_em,
            )
            evidencias.append(evidencia.pk)
            evidencia_ids.append(evidencia.pk)
        afirmacoes.append({"texto": _resumo_registro(dados), "evidencia_ids": evidencia_ids})
        resumos.append(_resumo_registro(dados))
        chave = dados.get("full_name") or dados.get("id")
        atual = (dados.get("licenca"), dados.get("description") or dados.get("resumo"))
        if chave in chaves and chaves[chave] != atual:
            contradicao = True
        chaves[chave] = atual
    return {
        "evidencias": evidencias,
        "afirmacoes": afirmacoes,
        "fonte_resumo": "\n".join(resumos),
        "contradicao": contradicao,
    }


@etapa("redigir")
def no_redigir(execucao, state):
    campos = configuracao.resolver(secao=state["secao"])
    prompt = campos.get("prompt") or PROMPT_PADRAO
    resposta = instrumentation.executar_texto(
        prompt,
        finalidade="redacao",
        etapa="redigir",
        execucao=execucao,
        fonte_texto=state.get("fonte_resumo", ""),
    )
    return {"texto": resposta.texto, "redacao_status": resposta.chamada.status}


@etapa("revisar")
def no_revisar(execucao, state):
    redacao_ok = state.get("redacao_status") == "sucesso" and bool(str(state.get("texto", "")).strip())
    return {
        "revisao": avaliar_revisao(state.get("afirmacoes", []), state.get("contradicao", False), redacao_ok)
    }


def avaliar_revisao(afirmacoes: list, contradicao: bool, redacao_ok: bool = True) -> dict:
    motivos = []
    if not afirmacoes or any(not a.get("evidencia_ids") for a in afirmacoes):
        motivos.append("evidencia_insuficiente")
    if not redacao_ok:
        motivos.append("geracao_falhou")
    if contradicao:
        motivos.append("contradicao_factual")
    return {"ok": not motivos, "motivos": motivos}


@etapa("ilustrar")
def no_ilustrar(execucao, state):
    try:
        return {"imagem": gerar_ilustracao(state.get("texto", "")[:80])}
    except Exception as exc:
        return {"imagem": {"ausente": True, "motivo": str(exc)}}


@etapa("salvar")
def no_salvar(execucao, state):
    revisao = state.get("revisao", {})
    aprovado_pela_revisao = bool(revisao.get("ok"))
    tipo = TipoConteudo.LISTA if state["secao"] in SECAO_TIPO else TipoConteudo.ARTIGO
    estado = EstadoConteudo.AGUARDANDO_REVISAO if aprovado_pela_revisao else EstadoConteudo.RASCUNHO
    afirmacoes = state.get("afirmacoes", [])
    titulo = afirmacoes[0]["texto"].split(":")[0] if afirmacoes else state["secao"]
    conteudo = Conteudo.objects.create(
        slug=f"{state['secao']}-{execucao.pk}", secao=state["secao"], tipo=tipo, estado=estado
    )
    metadados = {
        "evidencias": state.get("evidencias", []),
        "imagem": state.get("imagem", {}),
        "revisao": revisao,
    }
    if tipo == TipoConteudo.LISTA:
        metadados["aviso_curadoria"] = AVISO_CURADORIA
    versao = Versao.objects.create(
        conteudo=conteudo,
        titulo=titulo,
        resumo=state.get("fonte_resumo", "")[:500],
        corpo=state.get("texto", ""),
        metadados=metadados,
    )
    _criar_itens(versao, state.get("candidatos", []))
    conteudo.versao_em_edicao = versao
    conteudo.save(update_fields=["versao_em_edicao", "atualizado_em"])
    Evidencia.objects.filter(pk__in=state.get("evidencias", [])).update(versao=versao)
    return {
        "conteudo_id": conteudo.pk,
        "versao_id": versao.pk,
        "motivo": "; ".join(revisao.get("motivos", [])),
    }


def _criar_itens(versao: Versao, candidatos_ids: list) -> None:
    candidatos = Candidato.objects.filter(pk__in=candidatos_ids).select_related(
        "registro", "registro__fonte"
    )
    for ordem, candidato in enumerate(candidatos, start=1):
        tipo_item = "repositorio" if candidato.registro.fonte.tipo == TipoFonte.GITHUB else "modelo"
        Item.objects.create(versao=versao, ordem=ordem, tipo=tipo_item, dados=candidato.registro.dados)


def construir_grafo():
    grafo = StateGraph(EstadoPipeline)
    grafo.add_node("selecionar", no_selecionar)
    grafo.add_node("evidencias", no_evidencias)
    grafo.add_node("redigir", no_redigir)
    grafo.add_node("revisar", no_revisar)
    grafo.add_node("ilustrar", no_ilustrar)
    grafo.add_node("salvar", no_salvar)
    grafo.add_edge(START, "selecionar")
    grafo.add_edge("selecionar", "evidencias")
    grafo.add_edge("evidencias", "redigir")
    grafo.add_edge("redigir", "revisar")
    grafo.add_conditional_edges(
        "revisar",
        lambda state: "ilustrar" if state.get("revisao", {}).get("ok") else "salvar",
        {"ilustrar": "ilustrar", "salvar": "salvar"},
    )
    grafo.add_edge("ilustrar", "salvar")
    grafo.add_edge("salvar", END)
    return grafo.compile(checkpointer=InMemorySaver())


def executar_pipeline(*, tarefa=None, secao=Secao.DESTAQUES_GITHUB, execucao=None) -> Execucao:
    if execucao is None:
        snapshot = configuracao.capturar_snapshot(secao=secao, tarefa=tarefa)
        execucao = Execucao.objects.create(
            tipo="pipeline",
            estado=EstadoExecucao.EM_EXECUCAO,
            secao=secao,
            tarefa=tarefa,
            snapshot_config=snapshot,
            iniciado_em=timezone.now(),
        )
    else:
        execucao.estado = EstadoExecucao.EM_EXECUCAO
        execucao.iniciado_em = execucao.iniciado_em or timezone.now()
        execucao.save(update_fields=["estado", "iniciado_em"])

    state: EstadoPipeline = {"execucao_id": execucao.pk, "secao": secao}
    for etapa_concluida in execucao.etapas.order_by("id"):
        state.update(etapa_concluida.saida)

    try:
        grafo = construir_grafo()
        resultado = grafo.invoke(state, config={"configurable": {"thread_id": str(execucao.pk)}})
        execucao.estado = EstadoExecucao.CONCLUIDA
        execucao.motivo = resultado.get("motivo", "")
    except OrcamentoExcedido as exc:
        execucao.estado = EstadoExecucao.FALHOU_PARCIAL
        execucao.erro = str(exc)
    except Exception as exc:
        execucao.estado = EstadoExecucao.FALHOU
        execucao.erro = str(exc)
    execucao.finalizado_em = timezone.now()
    execucao.save(update_fields=["estado", "motivo", "erro", "finalizado_em"])
    return execucao
