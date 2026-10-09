import json
import threading
import unittest

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from content import services as content
from content.models import Conteudo, EstadoConteudo, Secao, Versao
from sources import services as sources
from sources.models import Fonte, TipoFonte


def gh_get(items):
    def _get(url, headers):
        return 200, {}, json.dumps({"items": items})

    return _get


def repo(id_, name, stars):
    return {
        "id": id_,
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "description": "d",
        "licenca": "MIT",
        "stargazers_count": stars,
    }


class CacheIndisponivelTests(TestCase):
    @override_settings(CACHES={"default": {"BACKEND": "tests.broken_cache.BrokenCache"}})
    def test_api_serve_da_fonte_de_verdade(self):
        conteudo = Conteudo.objects.create(slug="p1", secao=Secao.ARTIGOS, tipo="artigo")
        versao = Versao.objects.create(conteudo=conteudo, titulo="T", corpo="c")
        content.aprovar(versao)
        with self.captureOnCommitCallbacks(execute=True):
            content.publicar(conteudo, versao)

        self.assertEqual(self.client.get("/api/publico/home").status_code, 200)
        self.assertEqual(self.client.get("/api/publico/artigo/p1").status_code, 200)
        self.assertEqual(self.client.get("/api/publico/artigo/p1").json()["titulo"], "T")


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
        resposta = self.client.get("/api/publico/artigo/p1")
        self.assertEqual(resposta.json()["titulo"], "Publicado")


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
