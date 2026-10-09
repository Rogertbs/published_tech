from django.contrib import admin, messages

from jobs import services
from jobs.models import Agendamento, ConfiguracaoMotor, EventoTarefa, Tarefa


class EventoTarefaInline(admin.TabularInline):
    model = EventoTarefa
    extra = 0
    readonly_fields = ("nivel", "mensagem", "criado_em")
    can_delete = False


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tipo_tarefa",
        "estado",
        "origem",
        "tentativas",
        "prioridade",
        "agendado_para",
        "worker",
    )
    list_filter = ("estado", "origem", "tipo_tarefa")
    search_fields = ("tipo_tarefa", "chave_idempotencia")
    readonly_fields = (
        "reserva_token",
        "lease_expira_em",
        "worker",
        "tentativas",
        "iniciado_em",
        "finalizado_em",
        "resultado",
        "erro",
        "criado_em",
        "atualizado_em",
    )
    inlines = [EventoTarefaInline]


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo_tarefa", "intervalo_segundos", "ativo", "proxima_execucao")
    list_filter = ("ativo", "tipo_tarefa")


@admin.register(ConfiguracaoMotor)
class ConfiguracaoMotorAdmin(admin.ModelAdmin):
    list_display = ("__str__", "pausado", "automatico", "atualizado_em")
    actions = ["acao_pausar", "acao_ativar", "acao_executar_agora"]

    def has_add_permission(self, request):
        return not ConfiguracaoMotor.objects.exists()

    @admin.action(description="Pausar motor (cancela pendentes automáticas)")
    def acao_pausar(self, request, queryset):
        canceladas = services.pausar()
        self.message_user(request, f"Motor pausado. {canceladas} tarefa(s) automática(s) cancelada(s).")

    @admin.action(description="Ativar motor")
    def acao_ativar(self, request, queryset):
        services.ativar()
        self.message_user(request, "Motor ativado.")

    @admin.action(description="Executar agora (avulso)")
    def acao_executar_agora(self, request, queryset):
        try:
            tarefa, created = services.executar_agora("eco", {"mensagem": "execução avulsa"})
        except services.MotorPausado:
            self.message_user(request, "Motor pausado: não é possível executar.", level=messages.ERROR)
            return
        estado = "enfileirada" if created else "já existente"
        self.message_user(request, f"Execução avulsa {estado}: tarefa #{tarefa.pk}.")
