import json

from django.core.cache import cache
from django.test import TestCase

from ai.models import ChamadaIA
from content import services as content
from content.models import Conteudo, EstadoConteudo, Versao
from finance.reports import resumo
from pipeline.motor import executar_pipeline
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


class FluxoE2ETests(TestCase):
    def setUp(self):
        cache.clear()

    def test_fluxo_completo(self):
        fonte = Fonte.objects.create(
            nome="GitHub", tipo=TipoFonte.GITHUB, parametros={"selecao": 2, "min_estrelas": 1}
        )

        coleta = sources.coletar(
            fonte, http_get=gh_get([repo(1, "org/a", 500), repo(2, "org/b", 100)]), sleep=lambda s: None
        )
        self.assertEqual(coleta.estado, "ok")
        candidatos = sources.selecionar_candidatos(coleta)
        self.assertEqual(len(candidatos), 2)

        execucao = executar_pipeline(secao="destaques-github")
        self.assertEqual(execucao.estado, "concluida")
        conteudo = Conteudo.objects.get()
        versao = Versao.objects.get()
        self.assertEqual(conteudo.estado, EstadoConteudo.AGUARDANDO_REVISAO)

        content.aprovar(versao)
        with self.captureOnCommitCallbacks(execute=True):
            content.publicar(conteudo, versao)

        artigo = self.client.get(f"/api/publico/artigo/{conteudo.slug}")
        self.assertEqual(artigo.status_code, 200)
        self.assertEqual(len(artigo.json()["itens"]), 2)
        self.assertIn("Curadoria própria", artigo.json()["aviso_curadoria"])
        self.assertEqual(self.client.get("/api/publico/home").json()["destaques_github"][0]["slug"], conteudo.slug)

        v2 = content.editar(conteudo, titulo="v2")
        self.assertEqual(
            self.client.get(f"/api/publico/artigo/{conteudo.slug}").json()["titulo"], versao.titulo
        )
        content.aprovar(v2)
        with self.captureOnCommitCallbacks(execute=True):
            content.publicar(conteudo, v2)
        self.assertEqual(self.client.get(f"/api/publico/artigo/{conteudo.slug}").json()["titulo"], "v2")

        self.assertGreaterEqual(ChamadaIA.objects.count(), 1)
        self.assertGreaterEqual(resumo()["quantidade"], 1)

        with self.captureOnCommitCallbacks(execute=True):
            content.retirar(conteudo)
        self.assertEqual(self.client.get(f"/api/publico/artigo/{conteudo.slug}").status_code, 404)
        self.assertEqual(self.client.get("/api/publico/home").json()["destaques_github"], [])
