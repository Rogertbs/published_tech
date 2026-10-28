from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from auditoria.models import AuditoriaAdministrativa
from content import services
from content.models import Aprovacao, Conteudo, EstadoConteudo, Publicacao, Secao, Versao


class CicloDeVidaTests(TestCase):
    def make_conteudo(self, slug="post-1", secao=Secao.ARTIGOS):
        conteudo = Conteudo.objects.create(slug=slug, secao=secao, tipo="artigo")
        versao = Versao.objects.create(
            conteudo=conteudo, titulo="Título", resumo="Resumo", corpo="Corpo"
        )
        conteudo.versao_em_edicao = versao
        conteudo.save(update_fields=["versao_em_edicao"])
        return conteudo, versao

    def test_publicar_sem_aprovacao_falha(self):
        conteudo, versao = self.make_conteudo()
        with self.assertRaises(ValueError):
            services.publicar(conteudo, versao)

    def test_aprovar_e_publicar(self):
        conteudo, versao = self.make_conteudo()
        services.aprovar(versao)
        quando = timezone.now()
        publicacao = services.publicar(conteudo, versao, quando=quando)

        conteudo.refresh_from_db()
        self.assertEqual(conteudo.versao_publicada_id, versao.pk)
        self.assertTrue(conteudo.esta_publicado)
        self.assertIsNone(conteudo.versao_em_edicao_id)
        self.assertEqual(conteudo.publicado_em, quando)
        self.assertTrue(publicacao.ativa)
        self.assertEqual(Publicacao.objects.filter(conteudo=conteudo).count(), 1)

    def test_publicar_versao_de_outro_conteudo_falha(self):
        conteudo, _ = self.make_conteudo(slug="a")
        outro, versao_outro = self.make_conteudo(slug="b")
        services.aprovar(versao_outro)
        with self.assertRaises(ValueError):
            services.publicar(conteudo, versao_outro)

    def test_retirar_remove_do_publico(self):
        conteudo, versao = self.make_conteudo()
        services.aprovar(versao)
        services.publicar(conteudo, versao)

        services.retirar(conteudo)

        conteudo.refresh_from_db()
        self.assertFalse(conteudo.esta_publicado)
        self.assertIsNone(conteudo.publicado_em)
        self.assertFalse(Publicacao.objects.filter(conteudo=conteudo, retirado_em__isnull=True).exists())

    def test_aprovacao_registra_origem(self):
        _, versao = self.make_conteudo()
        aprovacao = services.aprovar(versao, origem=Aprovacao.Origem.HUMANO)
        self.assertEqual(aprovacao.origem, "humano")

    def test_publicar_duas_vezes_nao_duplica(self):
        conteudo, versao = self.make_conteudo()
        services.aprovar(versao)
        services.publicar(conteudo, versao)
        services.publicar(conteudo, versao)

        self.assertEqual(Publicacao.objects.filter(conteudo=conteudo, retirado_em__isnull=True).count(), 1)
        self.assertEqual(Publicacao.objects.filter(conteudo=conteudo).count(), 1)

    def test_publicar_nova_versao_retira_a_anterior(self):
        conteudo, v1 = self.make_conteudo()
        services.aprovar(v1)
        services.publicar(conteudo, v1)

        v2 = Versao.objects.create(conteudo=conteudo, titulo="v2", corpo="c2")
        conteudo.versao_em_edicao = v2
        conteudo.save(update_fields=["versao_em_edicao"])
        services.aprovar(v2)
        services.publicar(conteudo, v2)

        ativas = Publicacao.objects.filter(conteudo=conteudo, retirado_em__isnull=True)
        self.assertEqual(ativas.count(), 1)
        self.assertEqual(ativas.first().versao_id, v2.pk)

    def test_versao_publicavel_exige_aprovacao(self):
        conteudo, versao = self.make_conteudo()
        self.assertIsNone(services.versao_publicavel(conteudo))
        services.aprovar(versao)
        self.assertEqual(services.versao_publicavel(conteudo), versao)


class CicloEditorialTests(TestCase):
    def publicar_v1(self):
        conteudo = Conteudo.objects.create(slug="mat", secao=Secao.ARTIGOS, tipo="artigo")
        v1 = Versao.objects.create(conteudo=conteudo, titulo="v1", resumo="r", corpo="c1")
        conteudo.versao_em_edicao = v1
        conteudo.save(update_fields=["versao_em_edicao"])
        services.aprovar(v1)
        services.publicar(conteudo, v1)
        return conteudo, v1

    def test_editar_publicado_mantem_versao_publica(self):
        conteudo, v1 = self.publicar_v1()
        v2 = services.editar(conteudo, titulo="v2", corpo="c2")

        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.PUBLICADO_EM_EDICAO)
        self.assertEqual(conteudo.versao_publicada_id, v1.pk)
        self.assertEqual(conteudo.versao_em_edicao_id, v2.pk)
        ativa = Publicacao.objects.get(conteudo=conteudo, retirado_em__isnull=True)
        self.assertEqual(ativa.versao_id, v1.pk)

    def test_v2_nao_publicavel_sem_aprovacao(self):
        conteudo, v1 = self.publicar_v1()
        v2 = services.editar(conteudo, titulo="v2", corpo="c2")
        with self.assertRaises(ValueError):
            services.publicar(conteudo, v2)

    def test_publicar_v2_troca_ponteiro(self):
        conteudo, v1 = self.publicar_v1()
        v2 = services.editar(conteudo, titulo="v2", corpo="c2")
        services.aprovar(v2)
        services.publicar(conteudo, v2)

        conteudo.refresh_from_db()
        self.assertEqual(conteudo.versao_publicada_id, v2.pk)
        self.assertIsNone(conteudo.versao_em_edicao_id)
        self.assertEqual(conteudo.estado, EstadoConteudo.PUBLICADO)
        ativas = Publicacao.objects.filter(conteudo=conteudo, retirado_em__isnull=True)
        self.assertEqual(ativas.count(), 1)
        self.assertEqual(ativas.first().versao_id, v2.pk)

    def test_retirar_apos_edicao(self):
        conteudo, v1 = self.publicar_v1()
        services.editar(conteudo, titulo="v2", corpo="c2")
        services.retirar(conteudo)

        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.RETIRADO)
        self.assertIsNone(conteudo.versao_em_edicao_id)
        self.assertFalse(Publicacao.objects.filter(conteudo=conteudo, retirado_em__isnull=True).exists())

    def test_publicar_versao_antiga_com_edicao_nova_rejeitada(self):
        conteudo, v1 = self.publicar_v1()
        services.editar(conteudo, titulo="v2", corpo="c2")
        with self.assertRaises(ValueError):
            services.publicar(conteudo, v1)

    def test_aprovar_registra_regras_avaliadas(self):
        _, versao = self.publicar_v1()
        nova = Versao.objects.create(conteudo=versao.conteudo, titulo="v2")
        services.aprovar(nova, regras_avaliadas=["evidencia", "orcamento"])
        self.assertEqual(Aprovacao.objects.get(versao=nova).regras_avaliadas, ["evidencia", "orcamento"])

    def test_editar_com_itens_cria_nova_versao_de_itens(self):
        conteudo, v1 = self.publicar_v1()
        v2 = services.editar(
            conteudo,
            titulo="v2",
            itens=[{"tipo": "repositorio", "dados": {"full_name": "org/a"}}],
        )
        self.assertEqual(v2.itens.count(), 1)
        self.assertEqual(v2.itens.get().dados["full_name"], "org/a")

    def test_republicar_versao_aprovada_apos_retirada(self):
        conteudo, v1 = self.publicar_v1()
        services.retirar(conteudo)

        publicavel = services.versao_publicavel(conteudo)
        self.assertEqual(publicavel, v1)
        services.publicar(conteudo, publicavel)

        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.PUBLICADO)
        self.assertEqual(conteudo.versao_publicada_id, v1.pk)

    def test_aprovacao_registra_origem_responsavel_e_timestamp(self):
        _, versao = self.publicar_v1()
        aprovacao = Aprovacao.objects.get(versao=versao)
        self.assertEqual(aprovacao.origem, Aprovacao.Origem.HUMANO)
        self.assertIsNotNone(aprovacao.criado_em)
        self.assertIsInstance(aprovacao.regras_avaliadas, list)

    def test_acoes_registram_auditoria(self):
        conteudo, v1 = self.publicar_v1()
        v2 = services.editar(conteudo, titulo="v2")
        services.aprovar(v2)
        services.publicar(conteudo, v2)
        services.retirar(conteudo)

        acoes = set(AuditoriaAdministrativa.objects.values_list("acao", flat=True))
        self.assertTrue({"aprovar", "publicar", "editar", "retirar"}.issubset(acoes))


class AdminEditorialTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_superuser("editor", "editor@exemplo.com", "senha")
        self.client.force_login(usuario)

    def make_conteudo(self, estado=EstadoConteudo.AGUARDANDO_REVISAO):
        conteudo = Conteudo.objects.create(
            slug="admin-1", secao=Secao.ARTIGOS, tipo="artigo", estado=estado
        )
        versao = Versao.objects.create(conteudo=conteudo, titulo="Título", corpo="Corpo")
        conteudo.versao_em_edicao = versao
        conteudo.save(update_fields=["versao_em_edicao"])
        return conteudo, versao

    def test_index_tem_menu_de_producao(self):
        resposta = self.client.get("/admin/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Produção de notícias")
        self.assertContains(resposta, "Produção (tela única)")
        self.assertContains(resposta, "Revisar e aprovar")

    def test_aprovar_e_publicar_pela_pagina(self):
        conteudo, versao = self.make_conteudo()
        url = reverse("admin:content_conteudo_aprovar_publicar", args=[conteudo.pk])
        resposta = self.client.post(url)

        self.assertEqual(resposta.status_code, 302)
        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.PUBLICADO)
        self.assertEqual(conteudo.versao_publicada_id, versao.pk)

    def test_retirar_pela_pagina(self):
        conteudo, versao = self.make_conteudo()
        services.aprovar(versao)
        services.publicar(conteudo, versao)

        url = reverse("admin:content_conteudo_retirar", args=[conteudo.pk])
        resposta = self.client.post(url)

        self.assertEqual(resposta.status_code, 302)
        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.RETIRADO)

    def test_acao_em_massa_aprovar_e_publicar(self):
        conteudo, _ = self.make_conteudo()
        resposta = self.client.post(
            "/admin/content/conteudo/",
            {"action": "aprovar_e_publicar", "_selected_action": [str(conteudo.pk)]},
        )

        self.assertEqual(resposta.status_code, 302)
        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.PUBLICADO)

    def test_filtro_fila_revisao(self):
        self.make_conteudo()
        resposta = self.client.get("/admin/content/conteudo/?fila=revisao")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "admin-1")


class PublicadoFilterTests(TestCase):
    def setUp(self):
        cache.clear()

    def _com_ponteiro(self, slug, estado):
        conteudo = Conteudo.objects.create(slug=slug, secao=Secao.ARTIGOS, tipo="artigo")
        versao = Versao.objects.create(conteudo=conteudo, titulo="T", corpo="c")
        conteudo.versao_publicada = versao
        conteudo.publicado_em = timezone.now()
        conteudo.estado = estado
        conteudo.save()
        return conteudo

    def test_rejeitado_com_ponteiro_nao_aparece(self):
        self._com_ponteiro("rej", EstadoConteudo.REJEITADO)
        self.assertEqual(self.client.get("/api/publico/home").json()["artigos"], [])
        self.assertEqual(self.client.get("/api/publico/artigo/rej").status_code, 404)

    def test_publicado_sem_publicacao_ativa_nao_aparece(self):
        self._com_ponteiro("orf", EstadoConteudo.PUBLICADO)
        self.assertEqual(self.client.get("/api/publico/home").json()["artigos"], [])

    def test_publicado_com_publicacao_ativa_aparece(self):
        conteudo = Conteudo.objects.create(slug="ok", secao=Secao.ARTIGOS, tipo="artigo")
        versao = Versao.objects.create(conteudo=conteudo, titulo="T", corpo="c")
        conteudo.versao_em_edicao = versao
        conteudo.save(update_fields=["versao_em_edicao"])
        services.aprovar(versao)
        services.publicar(conteudo, versao)

        self.assertEqual(
            [i["slug"] for i in self.client.get("/api/publico/home").json()["artigos"]], ["ok"]
        )
