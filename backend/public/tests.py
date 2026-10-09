from django.core.cache import cache
from django.test import TestCase

from content import services
from content.models import Conteudo, Secao, Versao


class PublicApiTests(TestCase):
    def setUp(self):
        cache.clear()

    def make_publicado(self, slug="post-1", secao=Secao.ARTIGOS, titulo="Título", corpo="Corpo"):
        conteudo = Conteudo.objects.create(slug=slug, secao=secao, tipo="artigo")
        versao = Versao.objects.create(
            conteudo=conteudo, titulo=titulo, resumo="Resumo", corpo=corpo
        )
        services.aprovar(versao)
        services.publicar(conteudo, versao)
        return conteudo, versao

    def test_home_vazia(self):
        resp = self.client.get("/api/publico/home")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["artigos"], [])
        self.assertEqual(data["destaques_github"], [])
        self.assertEqual(data["radar_hf"], [])

    def test_home_lista_publicados(self):
        self.make_publicado(slug="p1", secao=Secao.ARTIGOS)
        self.make_publicado(slug="p2", secao=Secao.DESTAQUES_GITHUB, titulo="Repo")
        resp = self.client.get("/api/publico/home")
        data = resp.json()
        self.assertEqual([i["slug"] for i in data["artigos"]], ["p1"])
        self.assertEqual([i["slug"] for i in data["destaques_github"]], ["p2"])

    def test_artigo_publicado(self):
        self.make_publicado(slug="p1", corpo="Texto do corpo")
        resp = self.client.get("/api/publico/artigo/p1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["corpo"], "Texto do corpo")

    def test_rascunho_nao_e_publico(self):
        conteudo = Conteudo.objects.create(slug="rascunho", secao=Secao.ARTIGOS, tipo="artigo")
        Versao.objects.create(conteudo=conteudo, titulo="Rascunho", corpo="x")
        self.assertEqual(self.client.get("/api/publico/artigo/rascunho").status_code, 404)
        self.assertEqual(self.client.get("/api/publico/home").json()["artigos"], [])

    def test_secao_invalida_404(self):
        self.assertEqual(self.client.get("/api/publico/secao/inexistente").status_code, 404)

    def test_secao_lista(self):
        self.make_publicado(slug="p1", secao=Secao.ARTIGOS)
        resp = self.client.get("/api/publico/secao/artigos")
        self.assertEqual([i["slug"] for i in resp.json()["itens"]], ["p1"])

    def test_cache_serve_sem_reconsultar(self):
        conteudo, versao = self.make_publicado(slug="p1", titulo="Antigo")
        self.client.get("/api/publico/artigo/p1")  # popula o cache

        # Muda o título direto no banco, sem passar pelos serviços (sem invalidar).
        versao.titulo = "Novo (não invalidado)"
        versao.save(update_fields=["titulo"])

        resp = self.client.get("/api/publico/artigo/p1")
        self.assertEqual(resp.json()["titulo"], "Antigo")

    def test_publicar_nova_versao_invalida_cache(self):
        conteudo, versao = self.make_publicado(slug="p1", titulo="v1")
        self.client.get("/api/publico/artigo/p1")

        nova = Versao.objects.create(conteudo=conteudo, titulo="v2", corpo="c2")
        services.aprovar(nova)
        services.publicar(conteudo, nova)

        self.assertEqual(self.client.get("/api/publico/artigo/p1").json()["titulo"], "v2")

    def test_retirar_invalida_cache(self):
        self.make_publicado(slug="p1")
        self.client.get("/api/publico/home")
        self.client.get("/api/publico/artigo/p1")

        conteudo = Conteudo.objects.get(slug="p1")
        services.retirar(conteudo)

        self.assertEqual(self.client.get("/api/publico/home").json()["artigos"], [])
        self.assertEqual(self.client.get("/api/publico/artigo/p1").status_code, 404)
