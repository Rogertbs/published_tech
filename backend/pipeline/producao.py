import uuid

import markdown
import nh3
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from ai.models import ChamadaIA
from content import services as conteudo_services
from content.models import Aprovacao, Conteudo, EstadoConteudo
from jobs import services as jobs_services
from jobs.models import ConfiguracaoMotor, EstadoTarefa, Tarefa
from pipeline import services as pipeline_services
from pipeline.models import Evidencia, Execucao
from sources.models import Fonte, TipoFonte

TIPO_TAREFA = "noticia"
ESTADOS_EM_ANDAMENTO = {
    EstadoTarefa.PENDENTE,
    EstadoTarefa.RESERVADA,
    EstadoTarefa.EM_EXECUCAO,
}
ESTADOS_EM_REVISAO = (
    EstadoConteudo.AGUARDANDO_REVISAO,
    EstadoConteudo.RASCUNHO,
    EstadoConteudo.APROVADO,
)


def _render_markdown(texto: str) -> str:
    html = markdown.markdown(texto or "", extensions=["extra", "sane_lists"])
    return nh3.clean(html, link_rel="noopener noreferrer")


def _versao_atual(conteudo):
    if conteudo is None:
        return None
    if conteudo.versao_em_edicao_id:
        return conteudo.versao_em_edicao
    if conteudo.versao_publicada_id:
        return conteudo.versao_publicada
    return conteudo.versoes.order_by("-criado_em").first()


def _conteudo_da_tarefa(tarefa):
    resultado = tarefa.resultado or {}
    if resultado.get("conteudo"):
        return (
            Conteudo.objects.select_related("versao_em_edicao", "versao_publicada")
            .filter(slug=resultado["conteudo"])
            .first()
        )
    if resultado.get("versao"):
        from content.models import Versao

        versao = Versao.objects.select_related("conteudo").filter(pk=resultado["versao"]).first()
        return versao.conteudo if versao else None
    return None


def _url_publica(conteudo):
    if conteudo is None or not conteudo.esta_publicado:
        return ""
    base = getattr(settings, "SITE_PUBLICO_URL", "").rstrip("/")
    return f"{base}/artigo/{conteudo.slug}" if base else ""


def _dados_revisao(conteudo, tarefa=None):
    versao = _versao_atual(conteudo)
    metadados = versao.metadados if versao else {}
    revisao = metadados.get("revisao") or {}
    motivos = list(revisao.get("motivos") or [])
    motivo_tarefa = (tarefa.resultado or {}).get("motivo") if tarefa else ""
    if motivo_tarefa and motivo_tarefa not in motivos:
        motivos.append(motivo_tarefa)
    publicado = bool(
        conteudo
        and conteudo.esta_publicado
        and versao
        and conteudo.versao_publicada_id == versao.pk
    )
    return {
        "conteudo": conteudo,
        "versao": versao,
        "corpo_html": _render_markdown(versao.corpo) if versao else "",
        "motivos": motivos,
        "itens": versao.itens.all() if versao else [],
        "evidencias": versao.evidencias.all() if versao else [],
        "fontes": metadados.get("fontes") or [],
        "aprovada": bool(versao and versao.aprovada),
        "publicado": publicado,
        "url_publica": _url_publica(conteudo),
    }


def _execucao_do_conteudo(conteudo, tarefa=None):
    if conteudo is None:
        return None
    if tarefa is not None and (tarefa.resultado or {}).get("execucao"):
        execucao = Execucao.objects.filter(pk=tarefa.resultado["execucao"]).first()
        if execucao is not None:
            return execucao
    chamada = (
        ChamadaIA.objects.filter(conteudo_id=conteudo.pk, execucao__isnull=False)
        .select_related("execucao")
        .order_by("-id")
        .first()
    )
    if chamada is not None:
        return chamada.execucao
    evidencia = (
        Evidencia.objects.filter(versao__conteudo=conteudo, execucao__isnull=False)
        .select_related("execucao")
        .order_by("-id")
        .first()
    )
    return evidencia.execucao if evidencia is not None else None


def _nome_fonte(parametros):
    fonte_id = (parametros or {}).get("fonte_id")
    if isinstance(fonte_id, str) and fonte_id.isdigit():
        fonte_id = int(fonte_id)
    if not fonte_id:
        return "Automática"
    return Fonte.objects.filter(pk=fonte_id).values_list("nome", flat=True).first() or "—"


def _linhas_revisao(conteudos):
    return [
        {
            "conteudo": conteudo,
            "versao": _versao_atual(conteudo),
            "url_publica": _url_publica(conteudo),
        }
        for conteudo in conteudos
    ]


def _pode(user, perm):
    return user.has_perm(perm)


def _negar(request):
    messages.error(request, "Você não tem permissão para esta ação.")
    return redirect("admin:producao_index")


def _voltar(request):
    destino = request.POST.get("next") or reverse("admin:producao_index")
    if not url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        destino = reverse("admin:producao_index")
    return redirect(destino)


def index(request):
    if not _pode(request.user, "content.view_conteudo"):
        raise PermissionDenied
    fontes = Fonte.objects.filter(tipo=TipoFonte.RSS, habilitada=True).order_by("nome")
    motor_pausado = ConfiguracaoMotor.get_solo().pausado

    tarefa = None
    conteudo = None
    erro = ""
    tarefa_id = request.GET.get("tarefa", "")
    conteudo_id = request.GET.get("conteudo", "")

    if tarefa_id.isdigit():
        tarefa = Tarefa.objects.filter(pk=tarefa_id, tipo_tarefa=TIPO_TAREFA).first()
        if tarefa is None:
            erro = "Execução não encontrada."
        else:
            conteudo = _conteudo_da_tarefa(tarefa)
            if tarefa.estado == EstadoTarefa.FALHOU:
                erro = tarefa.erro or "A geração falhou."
            elif tarefa.estado in (EstadoTarefa.CANCELADA, EstadoTarefa.ABANDONADA):
                erro = "A execução foi cancelada."
    elif conteudo_id.isdigit():
        conteudo = (
            Conteudo.objects.select_related("versao_em_edicao", "versao_publicada")
            .filter(pk=conteudo_id)
            .first()
        )
        if conteudo is None:
            erro = "Conteúdo não encontrado."

    em_andamento = bool(
        tarefa and tarefa.estado in ESTADOS_EM_ANDAMENTO and conteudo is None
    )
    if not erro and tarefa and tarefa.estado == EstadoTarefa.CONCLUIDA and conteudo is None:
        resultado = tarefa.resultado or {}
        motivo = resultado.get("motivo") or resultado.get("erro")
        erro = f"Nenhum rascunho gerado: {motivo}." if motivo else "Nenhum rascunho gerado."

    revisao = _dados_revisao(conteudo, tarefa) if conteudo else None
    resultado = (tarefa.resultado or {}) if tarefa else {}
    falhou_geracao = "geracao_falhou" in (resultado.get("motivo") or "") or bool(
        revisao and "geracao_falhou" in revisao["motivos"]
    )
    revisao_vazia = bool(
        revisao and revisao["versao"] and not revisao["versao"].corpo.strip()
    )
    tem_conteudo = bool(
        revisao and revisao["versao"] and revisao["versao"].corpo.strip()
    )
    precisa_reprocessar = bool(
        revisao_vazia or (falhou_geracao and not tem_conteudo)
    )
    pode_reprocessar = bool(
        tarefa
        and tarefa.estado == EstadoTarefa.CONCLUIDA
        and resultado.get("execucao")
        and precisa_reprocessar
        and not (revisao and revisao["publicado"])
    )
    execucao_regerar = _execucao_do_conteudo(conteudo, tarefa) if conteudo else None
    pode_regerar = bool(
        execucao_regerar
        and revisao
        and revisao["versao"]
        and not revisao["publicado"]
        and not precisa_reprocessar
    )

    tarefas = [
        {"tarefa": tarefa, "fonte_nome": _nome_fonte(tarefa.parametros)}
        for tarefa in Tarefa.objects.filter(tipo_tarefa=TIPO_TAREFA).order_by("-id")[:10]
    ]
    fila = _linhas_revisao(
        Conteudo.objects.filter(estado__in=ESTADOS_EM_REVISAO)
        .select_related("versao_em_edicao", "versao_publicada")
        .order_by("-atualizado_em")[:10]
    )
    publicados = _linhas_revisao(
        Conteudo.objects.filter(estado=EstadoConteudo.PUBLICADO)
        .select_related("versao_em_edicao", "versao_publicada")
        .order_by("-publicado_em")[:5]
    )

    return render(
        request,
        "admin/producao/index.html",
        {
            "title": "Produção de notícias",
            "fontes": fontes,
            "motor_pausado": motor_pausado,
            "tarefa": tarefa,
            "tarefas": tarefas,
            "fila": fila,
            "publicados": publicados,
            "revisao": revisao,
            "erro": erro,
            "em_andamento": em_andamento,
            "falhou_geracao": falhou_geracao,
            "revisao_vazia": revisao_vazia,
            "precisa_reprocessar": precisa_reprocessar,
            "pode_reprocessar": pode_reprocessar,
            "pode_regerar": pode_regerar,
        },
    )


@require_POST
def criar(request):
    if not _pode(request.user, "content.add_conteudo"):
        return _negar(request)
    fonte_id = request.POST.get("fonte", "")
    if not fonte_id.isdigit():
        messages.error(request, "Escolha uma fonte RSS habilitada.")
        return redirect("admin:producao_index")
    fonte = Fonte.objects.filter(
        pk=fonte_id, tipo=TipoFonte.RSS, habilitada=True
    ).first()
    if fonte is None:
        messages.error(request, "Fonte RSS indisponível ou desabilitada.")
        return redirect("admin:producao_index")
    try:
        tarefa, _ = jobs_services.executar_agora(
            TIPO_TAREFA,
            {"fonte_id": fonte.pk},
            f"producao:{uuid.uuid4().hex}",
        )
    except jobs_services.MotorPausado:
        messages.error(request, "Motor pausado: ative o motor para gerar notícias.")
        return redirect("admin:producao_index")
    messages.success(request, f"Notícia enfileirada (tarefa #{tarefa.pk}).")
    return redirect(f"{reverse('admin:producao_index')}?tarefa={tarefa.pk}")


@require_GET
def tarefa_status(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk, tipo_tarefa=TIPO_TAREFA)
    return JsonResponse(
        {
            "estado": tarefa.estado,
            "em_andamento": tarefa.estado in ESTADOS_EM_ANDAMENTO,
            "erro": tarefa.erro,
        }
    )


def _alvo(request, pk):
    if not _pode(request.user, "content.change_conteudo"):
        return None
    return get_object_or_404(
        Conteudo.objects.select_related("versao_em_edicao", "versao_publicada"), pk=pk
    )


@require_POST
def aprovar(request, pk):
    conteudo = _alvo(request, pk)
    if conteudo is None:
        return _negar(request)
    versao = _versao_atual(conteudo)
    if versao is None:
        messages.error(request, "Não há versão para aprovar.")
        return _voltar(request)
    conteudo_services.aprovar(
        versao, aprovador=request.user, origem=Aprovacao.Origem.HUMANO
    )
    messages.success(request, "Versão aprovada.")
    return _voltar(request)


@require_POST
def publicar(request, pk):
    conteudo = _alvo(request, pk)
    if conteudo is None:
        return _negar(request)
    versao = conteudo_services.versao_publicavel(conteudo)
    if versao is None:
        messages.error(request, "Aprove a versão antes de publicar.")
        return _voltar(request)
    try:
        conteudo_services.publicar(conteudo, versao)
    except ValueError as exc:
        messages.error(request, str(exc))
        return _voltar(request)
    messages.success(request, "Notícia publicada.")
    return _voltar(request)


@require_POST
def aprovar_publicar(request, pk):
    conteudo = _alvo(request, pk)
    if conteudo is None:
        return _negar(request)
    versao = _versao_atual(conteudo)
    if versao is None:
        messages.error(request, "Não há versão para publicar.")
        return _voltar(request)
    conteudo_services.aprovar(
        versao, aprovador=request.user, origem=Aprovacao.Origem.HUMANO
    )
    try:
        conteudo_services.publicar(conteudo, versao)
    except ValueError as exc:
        messages.error(request, str(exc))
        return _voltar(request)
    messages.success(request, "Notícia aprovada e publicada.")
    return _voltar(request)


@require_POST
def rejeitar(request, pk):
    conteudo = _alvo(request, pk)
    if conteudo is None:
        return _negar(request)
    try:
        conteudo_services.rejeitar(conteudo, usuario=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return _voltar(request)
    messages.success(request, "Conteúdo rejeitado.")
    return redirect("admin:producao_index")


@require_POST
def retirar(request, pk):
    conteudo = _alvo(request, pk)
    if conteudo is None:
        return _negar(request)
    conteudo_services.retirar(conteudo)
    messages.success(request, "Conteúdo retirado do público.")
    return _voltar(request)


@require_POST
def reprocessar(request, pk):
    if not _pode(request.user, "content.change_conteudo"):
        return _negar(request)
    tarefa = get_object_or_404(Tarefa, pk=pk, tipo_tarefa=TIPO_TAREFA)
    resultado = tarefa.resultado or {}
    execucao_id = resultado.get("execucao")
    if not execucao_id:
        messages.error(request, "Esta execução não pode ser reprocessada.")
        return _voltar(request)
    execucao = get_object_or_404(Execucao, pk=execucao_id)
    conteudo = Conteudo.objects.filter(slug=f"{execucao.secao}-{execucao.pk}").first()
    if conteudo is not None and conteudo.esta_publicado:
        messages.error(request, "Conteúdo já publicado não pode ser reprocessado.")
        return _voltar(request)
    versao = _versao_atual(conteudo)
    vazio = not (versao and versao.corpo.strip())
    falhou = "geracao_falhou" in (resultado.get("motivo") or "")
    if not (vazio or (falhou and conteudo is None)):
        messages.error(
            request, "Este rascunho já tem conteúdo; edite ou gere uma nova notícia."
        )
        return _voltar(request)
    if ConfiguracaoMotor.get_solo().pausado:
        messages.error(request, "Motor pausado: ative o motor para reprocessar.")
        return _voltar(request)
    try:
        pipeline_services.preparar_retentativa(execucao)
    except ValueError as exc:
        messages.error(request, str(exc))
        return _voltar(request)
    nova, _ = jobs_services.executar_agora(
        TIPO_TAREFA,
        {"fonte_id": tarefa.parametros.get("fonte_id"), "execucao_id": execucao.pk},
        f"producao-retry:{uuid.uuid4().hex}",
    )
    messages.success(request, f"Reprocessamento enfileirado (tarefa #{nova.pk}).")
    return redirect(f"{reverse('admin:producao_index')}?tarefa={nova.pk}")


@require_POST
def editar(request, pk):
    conteudo = _alvo(request, pk)
    if conteudo is None:
        return _negar(request)
    titulo = request.POST.get("titulo", "").strip()
    resumo = request.POST.get("resumo", "").strip()
    corpo = request.POST.get("corpo", "").strip()
    if not titulo:
        messages.error(request, "Informe o título.")
        return _voltar(request)
    if len(titulo) > 300:
        messages.error(request, "O título deve ter no máximo 300 caracteres.")
        return _voltar(request)
    if not corpo:
        messages.error(request, "Informe o corpo do texto.")
        return _voltar(request)
    conteudo_services.editar(
        conteudo,
        titulo=titulo,
        resumo=resumo,
        corpo=corpo,
        usuario=request.user,
    )
    messages.success(request, "Edição salva como nova versão. Revise e aprove.")
    return _voltar(request)


@require_POST
def regerar(request, pk):
    if not _pode(request.user, "content.change_conteudo"):
        return _negar(request)
    conteudo = get_object_or_404(Conteudo, pk=pk)
    execucao = _execucao_do_conteudo(conteudo)
    if execucao is None:
        messages.error(request, "Não há execução associada para regerar esta notícia.")
        return _voltar(request)
    if ConfiguracaoMotor.get_solo().pausado:
        messages.error(request, "Motor pausado: ative o motor para regerar.")
        return _voltar(request)
    pipeline_services.preparar_regeracao(execucao)
    fonte_id = (
        execucao.tarefa.parametros.get("fonte_id")
        if execucao.tarefa is not None
        else None
    )
    nova, _ = jobs_services.executar_agora(
        TIPO_TAREFA,
        {
            "fonte_id": fonte_id,
            "execucao_id": execucao.pk,
            "regerar_conteudo_id": conteudo.pk,
        },
        f"producao-regerar:{uuid.uuid4().hex}",
    )
    messages.success(
        request,
        f"Regeração enfileirada (tarefa #{nova.pk}). A versão anterior fica no histórico.",
    )
    return redirect(f"{reverse('admin:producao_index')}?tarefa={nova.pk}")
