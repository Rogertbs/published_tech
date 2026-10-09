import json
import logging
import threading
import unittest
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from ai import instrumentation
from ai.providers import OpenRouterProvedor
from auditoria.models import AuditoriaAdministrativa
from content import services as content
from content.models import Conteudo, Publicacao, Secao, Versao
from content.services import HOME_KEY
from finance import services as orcamento
from finance.models import ConfiguracaoOrcamento, EventoOrcamento
from sources import services as sources
from sources.models import Fonte, TipoFonte
from tests.factories import gh_get, repo


class CacheIndisponivelTests(TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @override_settings(CACHES={"default": {"BACKEND": "tests.broken_cache.BrokenCache"}})
    def test_api_serve_da_fonte_de_verdade(self):
        conteudo = Conteudo.objects.create(slug="p1", secao=Secao.ARTIGOS, tipo="artigo")
        versao = Versao.objects.create(conteudo=conteudo, titulo="T", corpo="c")
        content.aprovar(versao)
        with self.captureOnCommitCallbacks(execute=True):
            content.publicar(conteudo, versao)

        self.assertEqual(self.client.get("/api/publico/home").status_code, 200)
        self.assertEqual(self.client.get("/api/publico/artigo/p1").json()["titulo"], "T")


class CacheRepopulaTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_cache_reconstroi_apos_perda(self):
        conteudo = Conteudo.objects.create(slug="p1", secao=Secao.ARTIGOS, tipo="artigo")
        versao = Versao.objects.create(conteudo=conteudo, titulo="T", corpo="c")
        content.aprovar(versao)
        with self.captureOnCommitCallbacks(execute=True):
            content.publicar(conteudo, versao)

        self.client.get("/api/publico/home")
        self.assertIsNotNone(cache.get(HOME_KEY))

        cache.clear()
        self.assertIsNone(cache.get(HOME_KEY))
        self.client.get("/api/publico/home")
        self.assertIsNotNone(cache.get(HOME_KEY))


class RascunhoIsoladoTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_rascunho_nunca_no_publico(self):
        conteudo = Conteudo.objects.create(slug="r", secao=Secao.ARTIGOS, tipo="artigo")
        Versao.objects.create(conteudo=conteudo, titulo="Rascunho", corpo="x")

        self.assertEqual(self.client.get("/api/publico/home").json()["artigos"], [])
        self.assertEqual(self.client.get("/api/publico/artigo/r").status_code, 404)

    def test_edicao_nao_vaza_rascunho_no_cache(self):
        conteudo = Conteudo.objects.create(slug="p1", secao=Secao.ARTIGOS, tipo="artigo")
        v1 = Versao.objects.create(conteudo=conteudo, titulo="Publicado", corpo="c1")
        content.aprovar(v1)
        with self.captureOnCommitCallbacks(execute=True):
            content.publicar(conteudo, v1)
        self.client.get("/api/publico/artigo/p1")

        content.editar(conteudo, titulo="Rascunho novo", corpo="c2")
        self.assertEqual(self.client.get("/api/publico/artigo/p1").json()["titulo"], "Publicado")


class FonteIndisponivelTests(TestCase):
    def test_falha_de_uma_fonte_marca_parcial(self):
        Fonte.objects.create(nome="Boa", tipo=TipoFonte.GITHUB, parametros={"min_estrelas": 1})
        Fonte.objects.create(nome="Ruim", tipo=TipoFonte.GITHUB, parametros={"min_estrelas": 999})

        def http_get(url, headers):
            if "999" in url:
                return 500, {}, "erro"
            return 200, {}, json.dumps({"items": [repo(1, "org/a", 100)]})

        resultado = sources.coletar_todas(http_get=http_get, sleep=lambda s: None)
        self.assertEqual(resultado["estado"], "falhou_parcial")


class RecuperacaoWorkerTests(TestCase):
    def test_lease_expirado_recupera_e_token_antigo_rejeitado(self):
        from jobs import services as jobs
        from jobs.models import EstadoTarefa, Tarefa

        Tarefa.objects.create(tipo_tarefa="eco")
        agora = timezone.now()
        antiga = jobs.reservar_proxima("w1", agora=agora)
        token_antigo = antiga.reserva_token

        jobs.recuperar_abandonadas(agora=agora + timedelta(seconds=9999))
        nova = jobs.reservar_proxima("w2")

        self.assertEqual(Tarefa.objects.get().estado, EstadoTarefa.RESERVADA)
        self.assertNotEqual(token_antigo, nova.reserva_token)
        with self.assertRaises(jobs.ReservaInvalida):
            jobs.concluir(antiga, token_antigo, {})


class OrcamentoBloqueiaTests(TestCase):
    def test_estouro_bloqueia_chamada_paga(self):
        config = ConfiguracaoOrcamento.get_solo()
        config.limite_diario = Decimal("0.001")
        config.save()
        chamadas = []

        def http_post(url, headers, body):
            chamadas.append(url)
            return 200, {}, json.dumps({"choices": [{"message": {"content": "x"}}]})

        provedor = OpenRouterProvedor(
            api_key="k", base_url="https://openrouter.ai/api/v1", modelo_padrao="m", http_post=http_post
        )
        with self.assertRaises(orcamento.OrcamentoExcedido):
            instrumentation.executar_texto(
                "x", finalidade="redacao", provedor=provedor, custo_estimado=Decimal("1.0")
            )

        self.assertEqual(chamadas, [])
        self.assertEqual(EventoOrcamento.objects.count(), 1)


class PublicacaoIdempotenteTests(TestCase):
    def test_publicar_mesma_versao_nao_duplica(self):
        conteudo = Conteudo.objects.create(slug="p1", secao=Secao.ARTIGOS, tipo="artigo")
        versao = Versao.objects.create(conteudo=conteudo, titulo="T", corpo="c")
        content.aprovar(versao)
        with self.captureOnCommitCallbacks(execute=True):
            content.publicar(conteudo, versao)
            content.publicar(conteudo, versao)

        ativas = Publicacao.objects.filter(conteudo=conteudo, retirado_em__isnull=True)
        self.assertEqual(ativas.count(), 1)


class AuditoriaTests(TestCase):
    def test_acoes_geram_auditoria(self):
        conteudo = Conteudo.objects.create(slug="p1", secao=Secao.ARTIGOS, tipo="artigo")
        versao = Versao.objects.create(conteudo=conteudo, titulo="T", corpo="c")
        content.aprovar(versao)
        with self.captureOnCommitCallbacks(execute=True):
            content.publicar(conteudo, versao)

        acoes = set(AuditoriaAdministrativa.objects.values_list("acao", flat=True))
        self.assertTrue({"aprovar", "publicar"}.issubset(acoes))


@unittest.skipUnless(connection.vendor == "postgresql", "requer PostgreSQL para SKIP LOCKED")
class ReservaConcorrenteTests(TransactionTestCase):
    def test_uma_reserva_por_tarefa(self):
        from django.db import connections

        from jobs import services as jobs
        from jobs.models import Tarefa

        Tarefa.objects.create(tipo_tarefa="eco")
        reservas = []
        trava = threading.Lock()

        def worker(worker_id):
            try:
                tarefa = jobs.reservar_proxima(worker_id)
                with trava:
                    reservas.append(tarefa.pk if tarefa else None)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len([r for r in reservas if r is not None]), 1)
