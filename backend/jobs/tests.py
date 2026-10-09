from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from jobs import services
from jobs.handlers import HANDLERS
from jobs.models import Agendamento, ConfiguracaoMotor, EstadoTarefa, OrigemTarefa, Tarefa


def _handler_falha(tarefa):
    raise RuntimeError("boom")


def _handler_observa(tarefa):
    return {"estado_durante": Tarefa.objects.get(pk=tarefa.pk).estado}


class FilaTests(TestCase):
    def enfileirar(self, **kwargs):
        defaults = dict(tipo_tarefa="eco", limite_tentativas=3)
        defaults.update(kwargs)
        return Tarefa.objects.create(**defaults)

    def test_enfileirar_e_processar(self):
        self.enfileirar(parametros={"mensagem": "oi"})
        self.assertTrue(services.processar_uma("w1"))

        tarefa = Tarefa.objects.get()
        self.assertEqual(tarefa.estado, EstadoTarefa.CONCLUIDA)
        self.assertEqual(tarefa.resultado["mensagem"], "oi")
        self.assertIsNone(tarefa.reserva_token)
        eventos = list(tarefa.eventos.values_list("mensagem", flat=True))
        self.assertTrue(any("reservada" in e for e in eventos))
        self.assertIn("concluída", eventos)

    def test_estado_em_execucao(self):
        HANDLERS["observa"] = _handler_observa
        try:
            self.enfileirar(tipo_tarefa="observa")
            services.processar_uma("w1")
            self.assertEqual(Tarefa.objects.get().resultado["estado_durante"], EstadoTarefa.EM_EXECUCAO)
        finally:
            HANDLERS.pop("observa", None)

    def test_dois_workers_nao_reservam_a_mesma(self):
        self.enfileirar()
        t1 = services.reservar_proxima("w1")
        t2 = services.reservar_proxima("w2")
        self.assertIsNotNone(t1)
        self.assertIsNone(t2)

    def test_token_invalido_rejeita_efeito(self):
        self.enfileirar()
        tarefa = services.reservar_proxima("w1")
        with self.assertRaises(services.ReservaInvalida):
            services.concluir(tarefa, "token-errado", {})
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.estado, EstadoTarefa.RESERVADA)

    def test_lease_expirado_devolve_a_fila(self):
        self.enfileirar()
        agora = timezone.now()
        tarefa = services.reservar_proxima("w1", agora=agora)
        self.assertEqual(tarefa.estado, EstadoTarefa.RESERVADA)

        recuperadas = services.recuperar_abandonadas(agora=agora + timedelta(seconds=9999))
        self.assertEqual(recuperadas, 1)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.estado, EstadoTarefa.PENDENTE)
        self.assertIsNone(tarefa.reserva_token)
        self.assertGreaterEqual(tarefa.tentativas, 1)
        self.assertIsNotNone(services.reservar_proxima("w2"))

    def test_worker_antigo_nao_grava_apos_recuperacao(self):
        self.enfileirar()
        agora = timezone.now()
        antiga = services.reservar_proxima("w1", agora=agora)
        token_antigo = antiga.reserva_token
        services.recuperar_abandonadas(agora=agora + timedelta(seconds=9999))
        nova = services.reservar_proxima("w2")
        self.assertNotEqual(token_antigo, nova.reserva_token)
        with self.assertRaises(services.ReservaInvalida):
            services.concluir(antiga, token_antigo, {})

    def test_lease_expirado_sem_tentativas_abandona(self):
        self.enfileirar(limite_tentativas=1)
        agora = timezone.now()
        services.reservar_proxima("w1", agora=agora)
        services.recuperar_abandonadas(agora=agora + timedelta(seconds=9999))
        self.assertEqual(Tarefa.objects.get().estado, EstadoTarefa.ABANDONADA)

    def test_retry_respeita_limite(self):
        HANDLERS["falha"] = _handler_falha
        try:
            self.enfileirar(tipo_tarefa="falha", limite_tentativas=2)
            services.processar_uma("w1")
            tarefa = Tarefa.objects.get()
            self.assertEqual(tarefa.estado, EstadoTarefa.PENDENTE)
            self.assertIn("boom", tarefa.erro)

            services.processar_uma("w1", agora=timezone.now() + timedelta(days=1))
            self.assertEqual(Tarefa.objects.get().estado, EstadoTarefa.FALHOU)
        finally:
            HANDLERS.pop("falha", None)

    def test_agendador_exige_flag_automatico(self):
        agora = timezone.now()
        ag = Agendamento.objects.create(
            tipo_tarefa="eco", intervalo_segundos=3600, proxima_execucao=agora
        )
        self.assertEqual(services.rodar_agendador(agora), 0)
        self.assertFalse(Tarefa.objects.exists())

        services.definir_automatico(True)
        self.assertEqual(services.rodar_agendador(agora), 1)
        self.assertTrue(Tarefa.objects.filter(chave_idempotencia=f"ag:{ag.pk}:{agora.isoformat()}").exists())

    def test_agendador_nao_duplica_ocorrencia(self):
        services.definir_automatico(True)
        agora = timezone.now()
        ag = Agendamento.objects.create(
            tipo_tarefa="eco", intervalo_segundos=3600, proxima_execucao=agora
        )
        self.assertEqual(services.rodar_agendador(agora), 1)
        chave = f"ag:{ag.pk}:{agora.isoformat()}"

        ag.proxima_execucao = agora
        ag.save(update_fields=["proxima_execucao"])
        self.assertEqual(services.rodar_agendador(agora), 0)
        self.assertEqual(Tarefa.objects.filter(chave_idempotencia=chave).count(), 1)

    def test_pausar_cancela_pendentes_automaticas(self):
        self.enfileirar(origem=OrigemTarefa.AUTOMATICO)
        self.enfileirar(origem=OrigemTarefa.MANUAL)
        canceladas = services.pausar()
        self.assertEqual(canceladas, 1)
        self.assertTrue(ConfiguracaoMotor.get_solo().pausado)
        self.assertEqual(
            Tarefa.objects.filter(estado=EstadoTarefa.CANCELADA, origem=OrigemTarefa.AUTOMATICO).count(), 1
        )
        self.assertEqual(Tarefa.objects.filter(origem=OrigemTarefa.MANUAL).count(), 1)

    def test_pausa_nao_consome_tentativa(self):
        self.enfileirar(origem=OrigemTarefa.AUTOMATICO)
        motor = ConfiguracaoMotor.get_solo()
        motor.pausado = True
        motor.save(update_fields=["pausado", "atualizado_em"])

        self.assertFalse(services.processar_uma("w1"))
        tarefa = Tarefa.objects.get()
        self.assertEqual(tarefa.estado, EstadoTarefa.PENDENTE)
        self.assertEqual(tarefa.tentativas, 0)

    def test_interrupcao_cooperativa(self):
        tarefa = self.enfileirar(origem=OrigemTarefa.AUTOMATICO)
        reservada = services.reservar_proxima("w1")
        services.pausar()
        reservada.refresh_from_db()
        self.assertTrue(reservada.interrupcao_solicitada)

        services.executar(reservada)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.estado, EstadoTarefa.PENDENTE)
        self.assertFalse(tarefa.interrupcao_solicitada)

    def test_executar_agora_recusa_pausado(self):
        services.pausar()
        with self.assertRaises(services.MotorPausado):
            services.executar_agora("eco")

    def test_executar_agora_idempotente(self):
        t1, c1 = services.executar_agora("eco", {"mensagem": "x"}, chave="k1")
        t2, c2 = services.executar_agora("eco", {"mensagem": "x"}, chave="k1")
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(t1.pk, t2.pk)
        self.assertEqual(Tarefa.objects.count(), 1)


class ApiExecucoesTests(TestCase):
    def test_post_cria_e_duplica_nao_repete(self):
        import json

        payload = json.dumps({"tipo": "eco", "chave_idempotencia": "abc"})
        r1 = self.client.post("/api/execucoes", payload, content_type="application/json")
        self.assertEqual(r1.status_code, 202)
        self.assertTrue(r1.json()["criada"])

        r2 = self.client.post("/api/execucoes", payload, content_type="application/json")
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.json()["criada"])
        self.assertEqual(Tarefa.objects.count(), 1)

    def test_post_sem_tipo_400(self):
        r = self.client.post("/api/execucoes", "{}", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_post_pausado_409(self):
        services.pausar()
        r = self.client.post(
            "/api/execucoes", '{"tipo": "eco"}', content_type="application/json"
        )
        self.assertEqual(r.status_code, 409)

    def test_get_status(self):
        tarefa, _ = services.executar_agora("eco", chave="z")
        r = self.client.get(f"/api/execucoes/{tarefa.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["estado"], EstadoTarefa.PENDENTE)

    @override_settings(INTERNAL_API_TOKEN="segredo")
    def test_post_exige_token(self):
        r = self.client.post(
            "/api/execucoes", '{"tipo": "eco"}', content_type="application/json"
        )
        self.assertEqual(r.status_code, 401)
        r = self.client.post(
            "/api/execucoes",
            '{"tipo": "eco"}',
            content_type="application/json",
            HTTP_X_INTERNAL_TOKEN="segredo",
        )
        self.assertEqual(r.status_code, 202)
