from django.test import TestCase
from django.utils import timezone

from content import services
from content.models import Aprovacao, Conteudo, Publicacao, Secao, Versao


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
