from typing import TypedDict

import hashlib
import re
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ai import instrumentation
from ai.models import ChamadaIA
from auditoria import services as auditoria
from configuracao import services as configuracao
from content.models import Conteudo, EstadoConteudo, Item, Secao, TipoConteudo, Versao
from finance.services import OrcamentoExcedido
from pipeline.imagens import gerar_ilustracao
from pipeline.models import EstadoExecucao, EtapaExecucao, Evidencia, Execucao
from sources.models import Candidato, Fonte, RegistroNormalizado, TipoFonte

SECAO_TIPO = {
    Secao.DESTAQUES_GITHUB: TipoFonte.GITHUB,
    Secao.RADAR_HF: TipoFonte.HUGGINGFACE,
    Secao.NOTICIAS: TipoFonte.RSS,
}
SECOES_LISTA = {Secao.DESTAQUES_GITHUB, Secao.RADAR_HF}
SECAO_TITULO = {
    Secao.DESTAQUES_GITHUB: "Destaques GitHub",
    Secao.RADAR_HF: "Radar Hugging Face",
}
TIPO_ITEM = {
    TipoFonte.GITHUB: Item.TipoItem.REPOSITORIO,
    TipoFonte.HUGGINGFACE: Item.TipoItem.MODELO,
}
AVISO_CURADORIA = "Curadoria própria — não é ranking oficial de terceiros."
PROMPT_PADRAO = (
    "Escreva em português do Brasil. Se as evidências estiverem em outro idioma, "
    "traduza-as. Comece com uma linha no formato 'TÍTULO: <título curto em português>' "
    "e depois redija uma análise curta e prática, com base apenas nas evidências."
)
PROMPT_CURADORIA = (
    "Você é curador editorial de tecnologia. Escreva em português do Brasil uma "
    "introdução curta (2 a 3 frases) para uma curadoria própria. Não invente fatos, "
    "métricas, rankings ou nomes que não estejam nas evidências e não diga que é um "
    "ranking oficial. Comece com uma linha exatamente no formato "
    "'TÍTULO: <título curto em português>' e depois a introdução."
)


class EstadoPipeline(TypedDict, total=False):
    execucao_id: int
    secao: str
    coleta_id: int
    candidatos: list
    candidatos_deduplicados: int
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


def _campos_da_execucao(execucao, secao: str) -> dict:
    if execucao.snapshot_config_id:
        return dict(execucao.snapshot_config.campos)
    return configuracao.resolver(secao=secao)


def _quantidade(secao: str, campos: dict) -> int:
    if "quantidade_itens" in campos:
        return max(1, min(int(campos["quantidade_itens"]), 5))
    tipo = SECAO_TIPO.get(secao)
    fonte = Fonte.objects.filter(tipo=tipo, habilitada=True).order_by("id").first() if tipo else None
    if fonte:
        return max(1, min(int(fonte.parametros.get("selecao", 1)), 5))
    return 1


def _config_deduplicacao(campos: dict) -> tuple[bool, int | None]:
    deduplicar = bool(campos.get("deduplicar_itens", True))
    janela = campos.get("deduplicacao_janela_dias")
    if janela in (None, ""):
        return deduplicar, None
    try:
        return deduplicar, max(0, int(janela))
    except (TypeError, ValueError):
        return deduplicar, None


def _unicos(candidatos, limite: int) -> tuple[list[Candidato], int]:
    vistos = set()
    selecionados = []
    duplicados = 0
    for candidato in candidatos:
        chave = (candidato.registro.fonte.tipo, candidato.registro.chave_externa)
        if chave in vistos:
            duplicados += 1
            continue
        vistos.add(chave)
        selecionados.append(candidato)
        if len(selecionados) >= limite:
            break
    return selecionados, duplicados


def _selecionar_candidatos(
    secao: str, campos: dict, coleta_id: int | None = None
) -> tuple[list[Candidato], int]:
    base = (
        Candidato.objects.filter(selecionado=True)
        .select_related("registro", "registro__fonte")
        .order_by("-pontuacao")
    )
    tipo = SECAO_TIPO.get(secao)
    if tipo:
        base = base.filter(registro__fonte__tipo=tipo)
    if coleta_id:
        base = base.filter(registro__coleta_id=coleta_id)

    limite = _quantidade(secao, campos)
    deduplicar, janela = _config_deduplicacao(campos)
    if not deduplicar:
        selecionados, duplicados = _unicos(base, limite)
        return selecionados, duplicados

    elegivel = Q(registro__usado_em__isnull=True)
    if janela is not None:
        elegivel |= Q(registro__usado_em__lt=timezone.now() - timedelta(days=janela))
    disponiveis = base.filter(elegivel)
    selecionados, duplicados = _unicos(disponiveis, limite)
    deduplicados = base.count() - disponiveis.count() + duplicados
    return selecionados, deduplicados


def _candidatos_de_origem(candidatos_ids: list) -> list[Candidato]:
    return list(
        Candidato.objects.filter(pk__in=candidatos_ids).select_related(
            "registro", "registro__fonte"
        )
    )


def _hash_origem(candidatos_ids: list) -> str:
    chaves = [
        f"{c.registro.fonte.tipo}:{c.registro.chave_externa}"
        for c in _candidatos_de_origem(candidatos_ids)
    ]
    if not chaves:
        return ""
    return hashlib.sha256("\n".join(sorted(chaves)).encode("utf-8")).hexdigest()


def _marcar_usados(candidatos_ids: list) -> None:
    ids = [c.registro_id for c in _candidatos_de_origem(candidatos_ids)]
    if ids:
        RegistroNormalizado.objects.filter(pk__in=ids).update(usado_em=timezone.now())


def _registrar_deduplicacao(execucao, state, motivo: str) -> None:
    auditoria.registrar(
        "deduplicacao",
        "Execucao",
        execucao.pk,
        depois={
            "secao": state.get("secao"),
            "motivo": motivo,
            "candidatos_deduplicados": state.get("candidatos_deduplicados", 0),
        },
    )


def _resumo_registro(dados: dict) -> str:
    nome = dados.get("full_name") or dados.get("id") or ""
    descricao = dados.get("description") or dados.get("resumo") or ""
    return f"{nome}: {descricao}".strip()


def _extrair_titulo(texto: str) -> tuple[str, str]:
    linhas = texto.splitlines()
    for indice, linha in enumerate(linhas[:5]):
        limpa = linha.strip().strip("*# ").strip()
        maiuscula = limpa.upper()
        if maiuscula.startswith("TÍTULO:") or maiuscula.startswith("TITULO:"):
            titulo = limpa.split(":", 1)[1].strip()
            restante = "\n".join(linhas[:indice] + linhas[indice + 1 :]).strip()
            return titulo, restante
    return "", texto


def _sem_markdown(texto: str) -> str:
    return re.sub(r"[*_`#>]+", "", texto).strip()


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
    campos = _campos_da_execucao(execucao, state["secao"])
    candidatos, deduplicados = _selecionar_candidatos(
        state["secao"], campos, coleta_id=state.get("coleta_id")
    )
    saida = {
        "candidatos": [c.pk for c in candidatos],
        "candidatos_deduplicados": deduplicados,
    }
    if state.get("coleta_id"):
        saida["coleta_id"] = state["coleta_id"]
    return saida


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


def _texto_curadoria(execucao, state) -> str:
    titulo = SECAO_TITULO.get(execucao.secao, execucao.secao)
    data = timezone.localdate().strftime("%d/%m/%Y")
    total = len(state.get("afirmacoes", []))
    return (
        f"TÍTULO: {titulo} — curadoria própria ({data})\n\n"
        f"Seleção própria com {total} itens em destaque. Coleta em {data}."
    )


def _curadoria_valida(texto: str) -> bool:
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    if not linhas:
        return False
    primeira = linhas[0].upper()
    if not (primeira.startswith("TÍTULO:") or primeira.startswith("TITULO:")):
        return False
    baixo = (texto or "").lower()
    ruins = (
        "não há dados",
        "nao ha dados",
        "conteúdo fornecido",
        "conteudo fornecido",
        "sem fornecer",
        "não contém",
        "nao contem",
    )
    return not any(trecho in baixo for trecho in ruins)


@etapa("redigir")
def no_redigir(execucao, state):
    campos = configuracao.resolver(secao=state["secao"])
    lista = execucao.secao in SECOES_LISTA
    prompt = campos.get("prompt") or (PROMPT_CURADORIA if lista else PROMPT_PADRAO)
    if state.get("regerar_conteudo_id"):
        prompt = (
            f"{prompt}\n\nReescreva com abordagem e vocabulário diferentes da versão "
            "anterior, mantendo os mesmos fatos e evidências."
        )
    resposta = instrumentation.executar_texto(
        prompt,
        finalidade="redacao",
        etapa="redigir",
        execucao=execucao,
        fonte_texto=state.get("fonte_resumo", ""),
    )
    if lista:
        texto = resposta.texto if _curadoria_valida(resposta.texto) else _texto_curadoria(execucao, state)
        return {"texto": texto, "redacao_status": "sucesso"}
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
    candidatos_ids = state.get("candidatos", [])
    revisao = state.get("revisao", {})
    alvo = None
    if state.get("regerar_conteudo_id"):
        alvo = Conteudo.objects.filter(pk=state["regerar_conteudo_id"]).first()
    campos = _campos_da_execucao(execucao, state["secao"])
    deduplicar, janela = _config_deduplicacao(campos)
    if not candidatos_ids and state.get("candidatos_deduplicados", 0) > 0:
        _registrar_deduplicacao(execucao, state, "sem_candidatos_novos")
        return {"motivo": "conteudo_duplicado"}
    hash_origem = _hash_origem(candidatos_ids)
    if deduplicar and hash_origem:
        recentes = Versao.objects.filter(hash_origem=hash_origem)
        if alvo is not None:
            recentes = recentes.exclude(conteudo=alvo)
        if janela is not None:
            recentes = recentes.filter(criado_em__gte=timezone.now() - timedelta(days=janela))
        if recentes.exists():
            _registrar_deduplicacao(execucao, state, "conteudo_identico")
            _marcar_usados(candidatos_ids)
            return {"motivo": "conteudo_duplicado"}
    aprovado_pela_revisao = bool(revisao.get("ok"))
    tipo = TipoConteudo.LISTA if state["secao"] in SECOES_LISTA else TipoConteudo.ARTIGO
    estado = EstadoConteudo.AGUARDANDO_REVISAO if aprovado_pela_revisao else EstadoConteudo.RASCUNHO
    afirmacoes = state.get("afirmacoes", [])
    titulo_gerado, corpo = _extrair_titulo(state.get("texto", ""))
    titulo = titulo_gerado or (afirmacoes[0]["texto"].split(":")[0] if afirmacoes else state["secao"])
    resumo = _sem_markdown(corpo)[:300] or state.get("fonte_resumo", "")[:500]
    if alvo is not None:
        conteudo = alvo
        if conteudo.esta_publicado:
            estado = EstadoConteudo.PUBLICADO_EM_EDICAO
    else:
        conteudo = Conteudo.objects.create(
            slug=f"{state['secao']}-{execucao.pk}", secao=state["secao"], tipo=tipo, estado=estado
        )
    metadados = {
        "evidencias": state.get("evidencias", []),
        "imagem": state.get("imagem", {}),
        "revisao": revisao,
        "fontes": _urls_fontes(candidatos_ids),
        "candidatos_deduplicados": state.get("candidatos_deduplicados", 0),
    }
    if alvo is not None and conteudo.versao_em_edicao_id:
        metadados["regerado_de"] = conteudo.versao_em_edicao_id
    if tipo == TipoConteudo.LISTA:
        metadados["aviso_curadoria"] = f"{AVISO_CURADORIA} Coleta em {timezone.now().date().isoformat()}."
    versao = Versao.objects.create(
        conteudo=conteudo,
        titulo=titulo,
        resumo=resumo,
        corpo=corpo,
        hash_origem=hash_origem,
        metadados=metadados,
    )
    if tipo == TipoConteudo.LISTA:
        _criar_itens(versao, candidatos_ids)
    conteudo.estado = estado
    conteudo.versao_em_edicao = versao
    conteudo.save(update_fields=["versao_em_edicao", "estado", "atualizado_em"])
    Evidencia.objects.filter(pk__in=state.get("evidencias", [])).update(versao=versao)
    ChamadaIA.objects.filter(execucao=execucao, conteudo_id__isnull=True).update(
        conteudo_id=conteudo.pk
    )
    _marcar_usados(candidatos_ids)
    return {
        "conteudo_id": conteudo.pk,
        "versao_id": versao.pk,
        "motivo": "; ".join(revisao.get("motivos", [])),
    }


def _urls_fontes(candidatos_ids: list) -> list:
    urls = []
    for candidato in Candidato.objects.filter(pk__in=candidatos_ids).select_related("registro"):
        dados = candidato.registro.dados
        url = dados.get("html_url") or dados.get("url")
        if url:
            urls.append(url)
    return urls


def _criar_itens(versao: Versao, candidatos_ids: list) -> None:
    candidatos = {
        candidato.pk: candidato
        for candidato in Candidato.objects.filter(pk__in=candidatos_ids).select_related(
            "registro", "registro__fonte"
        )
    }
    for ordem, candidato_id in enumerate(candidatos_ids, start=1):
        candidato = candidatos.get(candidato_id)
        if candidato is None:
            continue
        tipo_item = TIPO_ITEM.get(candidato.registro.fonte.tipo, Item.TipoItem.REPOSITORIO)
        Item.objects.create(
            versao=versao, ordem=ordem, tipo=tipo_item, dados=candidato.registro.dados
        )


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


def executar_pipeline(
    *, tarefa=None, secao=Secao.DESTAQUES_GITHUB, execucao=None, coleta=None
) -> Execucao:
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
    if coleta is not None:
        state["coleta_id"] = coleta.pk
    for etapa_concluida in execucao.etapas.order_by("id"):
        state.update(etapa_concluida.saida)
    if tarefa is not None and tarefa.parametros.get("regerar_conteudo_id"):
        state["regerar_conteudo_id"] = tarefa.parametros["regerar_conteudo_id"]

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
