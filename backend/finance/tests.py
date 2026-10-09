import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from ai import instrumentation
from ai.models import ChamadaIA, StatusChamada
from ai.providers import MockProvedor, OpenRouterProvedor, ProvedorTimeout
from finance import services
from finance.models import ConfiguracaoOrcamento, EstadoReserva, EventoOrcamento, ReservaOrcamento
from finance.reports import exportar_csv, resumo
from jobs.models import EventoTarefa, Tarefa
from jobs.services import expirar_eventos


def criar_chamada(provedor="openrouter", modelo="m", custo=None, finalidade="redacao"):
    return ChamadaIA.objects.create(
        provedor=provedor,
        modelo=modelo,
        finalidade=finalidade,
        iniciada_em=timezone.now(),
        status=StatusChamada.SUCESSO,
        custo=custo,
    )


def provedor_pago(calls=None):
    def http_post(url, headers, body):
        if calls is not None:
            calls.append(url)
        payload = {
            "id": "gen-1",
            "model": "m",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.00012},
        }
        return 200, {}, json.dumps(payload)

    return OpenRouterProvedor(api_key="k", base_url="https://openrouter.ai/api/v1", modelo_padrao="m", http_post=http_post)


class OrcamentoTests(TestCase):
    def config(self, diario="5", mensal="30"):
        config = ConfiguracaoOrcamento.get_solo()
        config.limite_diario = Decimal(diario)
        config.limite_mensal = Decimal(mensal)
        config.save()
        return config

    def test_valores_padrao(self):
        config = ConfiguracaoOrcamento.get_solo()
        self.assertEqual(config.limite_diario, Decimal("5"))
        self.assertEqual(config.limite_mensal, Decimal("30"))

    def test_reserva_dentro_do_limite(self):
        reserva = services.reservar(Decimal("1.0"), provedor="openrouter", modelo="m")
        self.assertEqual(reserva.estado, EstadoReserva.ATIVA)
        self.assertEqual(ReservaOrcamento.objects.filter(estado=EstadoReserva.ATIVA).count(), 1)

    def test_bloqueio_registra_evento(self):
        self.config(diario="1")
        with self.assertRaises(services.OrcamentoExcedido):
            services.reservar(Decimal("2.0"))
        evento = EventoOrcamento.objects.get()
        self.assertEqual(evento.limite_atingido, "diario")
        self.assertEqual(evento.valor_solicitado, Decimal("2.0"))

    def test_gasto_conta_chamadas_e_reservas(self):
        criar_chamada(custo=Decimal("1.0"))
        services.reservar(Decimal("0.5"))
        self.assertEqual(services.gasto_dia(), Decimal("1.5"))

    def test_reserva_conciliada_nao_duplica(self):
        chamada = criar_chamada(custo=Decimal("2.0"))
        reserva = services.reservar(Decimal("1.0"))
        services.conciliar(reserva, chamada)
        self.assertEqual(services.gasto_dia(), Decimal("2.0"))

    def test_executar_texto_pago_reserva_e_concilia(self):
        resultado = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_pago()
        )
        reserva = ReservaOrcamento.objects.get()
        self.assertEqual(reserva.estado, EstadoReserva.CONCILIADA)
        self.assertEqual(reserva.chamada_id, resultado.chamada.pk)
        self.assertEqual(services.gasto_dia(), Decimal("0.00012"))

    def test_bloqueio_impede_chamada(self):
        self.config(diario="0.001")
        calls = []
        with self.assertRaises(services.OrcamentoExcedido):
            instrumentation.executar_texto(
                "x", finalidade="redacao", provedor=provedor_pago(calls), custo_estimado=Decimal("1.0")
            )
        self.assertEqual(calls, [])
        self.assertEqual(ChamadaIA.objects.count(), 0)
        self.assertEqual(EventoOrcamento.objects.count(), 1)

    def test_mock_nao_reserva(self):
        instrumentation.executar_texto("x", finalidade="redacao", provedor=MockProvedor())
        self.assertEqual(ReservaOrcamento.objects.count(), 0)

    def test_incerto_conserva_custo_da_reserva(self):
        def http_post(url, headers, body):
            raise ProvedorTimeout("timeout")

        provedor = OpenRouterProvedor(
            api_key="k", base_url="https://openrouter.ai/api/v1", modelo_padrao="m", http_post=http_post
        )
        resultado = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor, custo_estimado=Decimal("0.03")
        )
        self.assertEqual(resultado.chamada.status, StatusChamada.TIMEOUT)
        self.assertEqual(resultado.chamada.custo, Decimal("0.03"))
        self.assertEqual(services.gasto_dia(), Decimal("0.03"))

    def test_reserva_expirada_nao_conta(self):
        reserva = services.reservar(Decimal("1.0"))
        ReservaOrcamento.objects.filter(pk=reserva.pk).update(
            expira_em=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(services.gasto_dia(), Decimal("0"))
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, EstadoReserva.EXPIRADA)


class RelatoriosTests(TestCase):
    def criar(self, provedor, custo, **extra):
        return criar_chamada(provedor=provedor, modelo="m", custo=custo) if not extra else ChamadaIA.objects.create(
            provedor=provedor,
            modelo="m",
            finalidade="redacao",
            iniciada_em=timezone.now(),
            status=StatusChamada.SUCESSO,
            custo=custo,
            **extra,
        )

    def test_resumo_e_csv(self):
        self.criar("openrouter", Decimal("1.0"))
        self.criar("openrouter", Decimal("2.0"))
        self.criar("mock", None)

        dados = resumo()
        self.assertEqual(dados["total"], Decimal("3.0"))
        self.assertEqual(dados["por_provedor"]["openrouter"], Decimal("3.0"))
        self.assertEqual(dados["quantidade"], 3)

        linhas = exportar_csv().strip().splitlines()
        self.assertEqual(linhas[0].split(",")[0], "id")
        self.assertIn("duracao_ms", linhas[0])
        self.assertEqual(len(linhas), 4)

    def test_agregacoes_por_tarefa_e_conteudo_e_etapa(self):
        tarefa = Tarefa.objects.create(tipo_tarefa="eco")
        self.criar("openrouter", Decimal("1.0"), tarefa=tarefa, conteudo_id=7, etapa="redigir")
        self.criar("openrouter", Decimal("2.0"), tarefa=tarefa, conteudo_id=7, etapa="revisar")

        dados = resumo({"etapa": "redigir"})
        self.assertEqual(dados["total"], Decimal("1.0"))
        dados = resumo()
        self.assertEqual(dados["por_tarefa"][str(tarefa.pk)], Decimal("3.0"))
        self.assertEqual(dados["por_conteudo"]["7"], Decimal("3.0"))

    def test_filtro_por_provedor(self):
        self.criar("openrouter", Decimal("1.0"))
        self.criar("mock", Decimal("5.0"))
        dados = resumo({"provedor": "mock"})
        self.assertEqual(dados["total"], Decimal("5.0"))

    def test_financeiro_sobrevive_a_purga_de_logs(self):
        self.criar("openrouter", Decimal("4.0"))
        tarefa = Tarefa.objects.create(tipo_tarefa="eco")
        evento = EventoTarefa.objects.create(tarefa=tarefa, mensagem="antigo")
        EventoTarefa.objects.filter(pk=evento.pk).update(
            criado_em=timezone.now() - timedelta(days=400)
        )

        removidos = expirar_eventos(timezone.now())
        self.assertEqual(removidos, 1)
        self.assertEqual(EventoTarefa.objects.count(), 0)
        self.assertEqual(resumo()["total"], Decimal("4.0"))
