from django.core.exceptions import ValidationError
from django.db import connection, transaction

from ai.prompts import envolver_fonte_como_dado
from auditoria import services as auditoria
from configuracao.models import (
    Configuracao,
    EscopoConfig,
    SnapshotConfiguracao,
    VersaoConfiguracao,
)

CAMPOS_PROTEGIDOS = {
    "texto_fonte_e_dado",
    "exigir_evidencia",
    "bloqueios_publicacao",
    "orcamento_obrigatorio",
}
PROTEGIDOS_PADRAO = {chave: True for chave in CAMPOS_PROTEGIDOS}
PRESETS = {
    "direto": {"tom": "direto", "humor": "leve"},
    "analitico": {"tom": "analitico", "humor": "nenhum"},
}


def registrar_auditoria(acao, entidade, entidade_id, *, usuario=None, antes=None, depois=None):
    return auditoria.registrar(
        acao, entidade, entidade_id, usuario=usuario, antes=antes, depois=depois
    )


def _validar(campos: dict, escopo: str):
    if "prompt" in campos and not str(campos["prompt"]).strip():
        raise ValidationError("O campo 'prompt' não pode ficar vazio.")
    if escopo == EscopoConfig.AGENTE and not str(campos.get("prompt", "")).strip():
        raise ValidationError("Configuração de agente exige um 'prompt' não vazio.")
    if escopo != EscopoConfig.SISTEMA:
        indevidos = CAMPOS_PROTEGIDOS.intersection(campos)
        if indevidos:
            raise ValidationError(
                f"Campos protegidos não podem ser definidos no escopo '{escopo}': {sorted(indevidos)}."
            )


def _lock_config(configuracao: Configuracao) -> Configuracao:
    qs = Configuracao.objects.filter(pk=configuracao.pk)
    if connection.vendor == "postgresql":
        qs = qs.select_for_update()
    return qs.get()


def criar_versao(
    configuracao: Configuracao, campos: dict, *, ativar: bool = False, usuario=None
) -> VersaoConfiguracao:
    _validar(campos, configuracao.escopo)
    with transaction.atomic():
        configuracao = _lock_config(configuracao)
        ultima = configuracao.versoes.order_by("-numero").first()
        numero = (ultima.numero if ultima else 0) + 1
        versao = VersaoConfiguracao.objects.create(
            configuracao=configuracao, numero=numero, campos=campos, criada_por=usuario
        )
        registrar_auditoria(
            "criar_versao", "VersaoConfiguracao", versao.pk, usuario=usuario, depois=campos
        )
    if ativar:
        ativar_versao(versao, usuario=usuario)
    return versao


def ativar_versao(versao: VersaoConfiguracao, usuario=None) -> VersaoConfiguracao:
    anteriores = list(
        versao.configuracao.versoes.filter(ativa=True).values_list("pk", flat=True)
    )
    versao.configuracao.versoes.exclude(pk=versao.pk).update(ativa=False)
    versao.ativa = True
    versao.save(update_fields=["ativa"])
    registrar_auditoria(
        "ativar_versao",
        "VersaoConfiguracao",
        versao.pk,
        usuario=usuario,
        antes={"ativas": anteriores},
        depois={"ativa": versao.pk},
    )
    return versao


def comparar(versao_a: VersaoConfiguracao, versao_b: VersaoConfiguracao) -> dict:
    chaves = set(versao_a.campos) | set(versao_b.campos)
    return {
        chave: {"antes": versao_a.campos.get(chave), "depois": versao_b.campos.get(chave)}
        for chave in sorted(chaves)
        if versao_a.campos.get(chave) != versao_b.campos.get(chave)
    }


def restaurar(versao: VersaoConfiguracao, *, ativar: bool = False, usuario=None) -> VersaoConfiguracao:
    nova = criar_versao(versao.configuracao, dict(versao.campos), ativar=ativar, usuario=usuario)
    registrar_auditoria(
        "restaurar", "VersaoConfiguracao", nova.pk, usuario=usuario, antes={"origem": versao.pk}
    )
    return nova


def criar_versao_de_preset(configuracao: Configuracao, nome: str, *, ativar=True, usuario=None):
    if nome not in PRESETS:
        raise ValidationError(f"Preset desconhecido: {nome}.")
    return criar_versao(configuracao, dict(PRESETS[nome]), ativar=ativar, usuario=usuario)


def _camadas(secao: str = "", agente: str = ""):
    return [
        (EscopoConfig.SISTEMA, ""),
        (EscopoConfig.GERAL, ""),
        (EscopoConfig.SECAO, secao),
        (EscopoConfig.AGENTE, agente),
    ]


def _campos_e_versao(escopo: str, alvo: str = ""):
    filtro = {"secao": alvo} if escopo == EscopoConfig.SECAO else {"agente": alvo} if escopo == EscopoConfig.AGENTE else {}
    configuracao = Configuracao.objects.filter(escopo=escopo, **filtro).first()
    if configuracao is None:
        return {}, None
    versao = configuracao.versoes.filter(ativa=True).first()
    if versao is None:
        return {}, None
    return dict(versao.campos), versao


def resolver(secao: str = "", agente: str = "") -> dict:
    resultado = dict(PROTEGIDOS_PADRAO)
    camadas = _camadas(secao, agente)
    sistema, _ = _campos_e_versao(EscopoConfig.SISTEMA)
    resultado.update(sistema)
    for escopo, alvo in camadas[1:]:
        campos, _ = _campos_e_versao(escopo, alvo)
        for chave, valor in campos.items():
            if chave in CAMPOS_PROTEGIDOS:
                continue
            resultado[chave] = valor
    for chave in CAMPOS_PROTEGIDOS:
        if chave in sistema:
            resultado[chave] = sistema[chave]
    return resultado


def capturar_snapshot(secao: str = "", agente: str = "", tarefa=None) -> SnapshotConfiguracao:
    campos = resolver(secao=secao, agente=agente)
    versoes = {}
    for escopo, alvo in _camadas(secao, agente):
        _, versao = _campos_e_versao(escopo, alvo)
        if versao is not None:
            versoes[versao.configuracao.chave] = versao.numero
    return SnapshotConfiguracao.objects.create(tarefa=tarefa, campos=campos, versoes=versoes)


def montar_prompt_com_fonte(texto_fonte: str) -> str:
    return envolver_fonte_como_dado(texto_fonte)


def testar_prompt(prompt: str, *, entrada: str = "", provedor=None, correlacao=None):
    if not prompt or not prompt.strip():
        raise ValidationError("O prompt não pode ficar vazio.")
    from ai import instrumentation

    return instrumentation.executar_texto(
        prompt,
        finalidade="teste_prompt",
        etapa="previa_privada",
        provedor=provedor,
        correlacao=correlacao or {"origem": "previa_privada"},
        fonte_texto=entrada or None,
    )
