from typing import TypedDict

from django.utils import timezone
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ai import instrumentation
from configuracao import services as configuracao
from content.models import Conteudo, EstadoConteudo, Secao, TipoConteudo, Versao
from finance.services import OrcamentoExcedido
from pipeline.imagens import gerar_ilustracao
from pipeline.models import EstadoExecucao, EtapaExecucao, Evidencia, Execucao
from sources.models import Candidato, TipoFonte

SECAO_TIPO = {
    Secao.DESTAQUES_GITHUB: TipoFonte.GITHUB,
    Secao.RADAR_HF: TipoFonte.HUGGINGFACE,
}
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
    revisao: dict
    imagem: dict
    conteudo_id: int
    versao_id: int
    motivo: str


def _selecionar_candidatos(secao: str) -> list[Candidato]:
    qs = (
        Candidato.objects.filter(selecionado=True)
        .select_related("registro", "registro__fonte")
        .order_by("-pontuacao")
    )
    tipo = SECAO_TIPO.get(secao)
    if tipo:
        qs = qs.filter(registro__fonte__tipo=tipo)
    return list(qs[:5])


def _resumo_registro(dados: dict) -> str:
    nome = dados.get("full_name") or dados.get("id") or ""
    descricao = dados.get("description") or dados.get("resumo") or ""
    return f"{nome}: {descricao}".strip()


def etapa(nome):
    def decorator(fn):
        def wrapper(state: EstadoPipeline) -> dict:
            execucao = Execucao.objects.get(pk=state["execucao_id"])
            existente = EtapaExecucao.objects.filter(execucao=execucao, nome=nome).first()
            if existente is not None:
                return existente.saida
            saida = fn(execucao, state)
            EtapaExecucao.objects.create(execucao=execucao, nome=nome, saida=saida)
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
        evidencia = Evidencia.objects.create(
            execucao=execucao,
            fonte=registro.fonte,
            registro=registro,
            tipo=registro.fonte.tipo,
            url=dados.get("html_url") or dados.get("url") or "",
            trecho=dados.get("description") or dados.get("resumo") or "",
            coletado_em=registro.coletado_em,
        )
        evidencias.append(evidencia.pk)
        afirmacoes.append({"texto": _resumo_registro(dados), "evidencia_ids": [evidencia.pk]})
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
    return {"texto": resposta.texto}


@etapa("revisar")
def no_revisar(execucao, state):
    return {"revisao": avaliar_revisao(state.get("afirmacoes", []), state.get("contradicao", False))}


def avaliar_revisao(afirmacoes: list, contradicao: bool) -> dict:
    motivos = []
    if not afirmacoes:
        motivos.append("sem_afirmacoes")
    if any(not a.get("evidencia_ids") for a in afirmacoes):
        motivos.append("afirmacao_sem_evidencia")
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
    versao = Versao.objects.create(
        conteudo=conteudo,
        titulo=titulo,
        resumo=state.get("fonte_resumo", "")[:500],
        corpo=state.get("texto", ""),
        metadados={
            "evidencias": state.get("evidencias", []),
            "imagem": state.get("imagem", {}),
            "revisao": revisao,
        },
    )
    Evidencia.objects.filter(pk__in=state.get("evidencias", [])).update(versao=versao)
    return {
        "conteudo_id": conteudo.pk,
        "versao_id": versao.pk,
        "motivo": "; ".join(revisao.get("motivos", [])),
    }


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
    grafo.add_edge("revisar", "ilustrar")
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
        execucao.erro = resultado.get("motivo", "")
    except OrcamentoExcedido as exc:
        execucao.estado = EstadoExecucao.FALHOU_PARCIAL
        execucao.erro = str(exc)
    except Exception as exc:
        execucao.estado = EstadoExecucao.FALHOU
        execucao.erro = str(exc)
    execucao.finalizado_em = timezone.now()
    execucao.save(update_fields=["estado", "erro", "finalizado_em"])
    return execucao
