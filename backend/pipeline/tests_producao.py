from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from content import services as conteudo_services
from content.models import Conteudo, EstadoConteudo, Item, Versao
from jobs.models import ConfiguracaoMotor, EstadoTarefa, Tarefa
from pipeline import motor
from pipeline.models import EstadoExecucao, EtapaExecucao, Evidencia, Execucao
from sources.models import Fonte, TipoFonte


class ProducaoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "editor", "editor@exemplo.com", "senha"
        )
        self.client.force_login(self.user)
        self.fonte = Fonte.objects.create(
            tipo=TipoFonte.RSS, nome="Fonte RSS", parametros={"feed_url": "http://exemplo/feed"}
        )

    def make_conteudo(
        self,
        estado=EstadoConteudo.AGUARDANDO_REVISAO,
        slug="noticias-1",
        corpo="# Corpo\n\nTexto da notícia.",
    ):
        conteudo = Conteudo.objects.create(
            slug=slug, secao="noticias", tipo="artigo", estado=estado
        )
        versao = Versao.objects.create(
            conteudo=conteudo,
            titulo="Título de teste",
            resumo="Resumo",
            corpo=corpo,
        )
        conteudo.versao_em_edicao = versao
        conteudo.save(update_fields=["versao_em_edicao"])
        return conteudo, versao

    def make_falha(self, corpo=""):
        execucao = Execucao.objects.create(
            tipo="pipeline",
            estado=EstadoExecucao.CONCLUIDA,
            secao="noticias",
            iniciado_em=timezone.now(),
            motivo="geracao_falhou",
        )
        conteudo, versao = self.make_conteudo(
            estado=EstadoConteudo.RASCUNHO,
            slug=f"noticias-{execucao.pk}",
            corpo=corpo,
        )
        EtapaExecucao.objects.create(
            execucao=execucao, nome="selecionar", saida={"candidatos": [1]}
        )
        EtapaExecucao.objects.create(
            execucao=execucao, nome="evidencias", saida={"evidencias": []}
        )
        EtapaExecucao.objects.create(
            execucao=execucao,
            nome="redigir",
            saida={"texto": corpo, "redacao_status": "incerto"},
        )
        EtapaExecucao.objects.create(
            execucao=execucao,
            nome="salvar",
            saida={"conteudo_id": conteudo.pk, "versao_id": versao.pk},
        )
        Evidencia.objects.create(
            execucao=execucao,
            versao=versao,
            tipo="rss",
            url="http://exemplo/noticia",
            trecho="Trecho da evidência",
        )
        tarefa = Tarefa.objects.create(
            tipo_tarefa="noticia",
            estado=EstadoTarefa.CONCLUIDA,
            parametros={"fonte_id": self.fonte.pk},
            resultado={
                "execucao": execucao.pk,
                "conteudo": conteudo.slug,
                "versao": versao.pk,
                "motivo": "geracao_falhou",
            },
        )
        return tarefa, execucao, conteudo

    def test_index_exige_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("admin:producao_index"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/admin/login/", resposta["Location"])

    def test_index_mostra_formulario_e_fila(self):
        self.make_conteudo()
        resposta = self.client.get(reverse("admin:producao_index"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Gerar notícia")
        self.assertContains(resposta, "Título de teste")
        self.assertContains(resposta, "Fonte RSS")

    def test_criar_enfileira_noticia(self):
        resposta = self.client.post(
            reverse("admin:producao_criar"), {"fonte": self.fonte.pk}
        )
        self.assertEqual(resposta.status_code, 302)
        tarefa = Tarefa.objects.get()
        self.assertEqual(tarefa.tipo_tarefa, "noticia")
        self.assertEqual(tarefa.parametros["fonte_id"], self.fonte.pk)
        self.assertIn(f"tarefa={tarefa.pk}", resposta["Location"])

    def test_criar_ignora_fonte_nao_rss(self):
        outra = Fonte.objects.create(tipo=TipoFonte.GITHUB, nome="GitHub")
        self.client.post(reverse("admin:producao_criar"), {"fonte": outra.pk})
        self.assertFalse(Tarefa.objects.exists())

    def test_criar_com_motor_pausado(self):
        ConfiguracaoMotor.objects.update_or_create(pk=1, defaults={"pausado": True})
        self.client.post(reverse("admin:producao_criar"), {"fonte": self.fonte.pk})
        self.assertFalse(Tarefa.objects.exists())

    def test_aprovar_e_publicar_pela_tela(self):
        conteudo, versao = self.make_conteudo()
        resposta = self.client.post(
            reverse("admin:producao_aprovar_publicar", args=[conteudo.pk])
        )
        self.assertEqual(resposta.status_code, 302)
        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.PUBLICADO)
        self.assertEqual(conteudo.versao_publicada_id, versao.pk)
        self.assertTrue(versao.aprovada)

    def test_publicar_exige_aprovacao(self):
        conteudo, _ = self.make_conteudo()
        self.client.post(reverse("admin:producao_publicar", args=[conteudo.pk]))
        conteudo.refresh_from_db()
        self.assertFalse(conteudo.esta_publicado)

    def test_aprovar_sem_publicar(self):
        conteudo, versao = self.make_conteudo()
        self.client.post(reverse("admin:producao_aprovar", args=[conteudo.pk]))
        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.APROVADO)
        self.assertTrue(versao.aprovada)

    def test_rejeitar(self):
        conteudo, _ = self.make_conteudo()
        self.client.post(reverse("admin:producao_rejeitar", args=[conteudo.pk]))
        conteudo.refresh_from_db()
        self.assertEqual(conteudo.estado, EstadoConteudo.REJEITADO)

    def test_retirar(self):
        conteudo, versao = self.make_conteudo()
        conteudo_services.aprovar(versao)
        conteudo_services.publicar(conteudo, versao)
        self.client.post(reverse("admin:producao_retirar", args=[conteudo.pk]))
        conteudo.refresh_from_db()
        self.assertFalse(conteudo.esta_publicado)

    def test_status_da_tarefa(self):
        tarefa = Tarefa.objects.create(
            tipo_tarefa="noticia", parametros={}, estado=EstadoTarefa.PENDENTE
        )
        resposta = self.client.get(
            reverse("admin:producao_tarefa_status", args=[tarefa.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["em_andamento"])

    def test_revisao_mostra_rascunho_da_tarefa(self):
        conteudo, versao = self.make_conteudo()
        tarefa = Tarefa.objects.create(
            tipo_tarefa="noticia",
            parametros={"fonte_id": self.fonte.pk},
            estado=EstadoTarefa.CONCLUIDA,
            resultado={
                "conteudo": conteudo.slug,
                "versao": versao.pk,
                "fonte": self.fonte.nome,
                "estado_conteudo": conteudo.estado,
                "motivo": "",
            },
        )
        resposta = self.client.get(
            reverse("admin:producao_index") + f"?tarefa={tarefa.pk}"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Título de teste")
        self.assertContains(resposta, "Aprovar e publicar")
        self.assertContains(resposta, "<h1>Corpo</h1>", html=True)

    def test_revisao_por_conteudo_existente(self):
        conteudo, _ = self.make_conteudo()
        resposta = self.client.get(
            reverse("admin:producao_index") + f"?conteudo={conteudo.pk}"
        )
        self.assertContains(resposta, "Título de teste")

    def test_sem_permissao_nao_cria(self):
        staff = get_user_model().objects.create_user(
            "somente-staff", "staff@exemplo.com", "senha", is_staff=True
        )
        self.client.force_login(staff)
        self.client.post(reverse("admin:producao_criar"), {"fonte": self.fonte.pk})
        self.assertFalse(Tarefa.objects.exists())

    def test_gerar_novamente_reprocessa_mesma_execucao(self):
        tarefa, execucao, conteudo = self.make_falha()
        resposta = self.client.post(
            reverse("admin:producao_reprocessar", args=[tarefa.pk])
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Conteudo.objects.filter(pk=conteudo.pk).exists())
        etapas = set(
            EtapaExecucao.objects.filter(execucao=execucao).values_list("nome", flat=True)
        )
        self.assertEqual(etapas, {"selecionar", "evidencias"})
        nova = Tarefa.objects.exclude(pk=tarefa.pk).get()
        self.assertEqual(nova.tipo_tarefa, "noticia")
        self.assertEqual(nova.parametros["execucao_id"], execucao.pk)
        self.assertIn(f"tarefa={nova.pk}", resposta["Location"])

    def test_nao_reprocessa_rascunho_com_texto(self):
        tarefa, execucao, conteudo = self.make_falha(corpo="Texto existente")
        self.client.post(reverse("admin:producao_reprocessar", args=[tarefa.pk]))
        self.assertTrue(Conteudo.objects.filter(pk=conteudo.pk).exists())
        self.assertEqual(Tarefa.objects.count(), 1)

    def test_tela_mostra_itens_da_curadoria(self):
        conteudo, versao = self.make_conteudo(slug="destaques-github-1")
        conteudo.secao = "destaques-github"
        conteudo.tipo = "lista"
        conteudo.save(update_fields=["secao", "tipo"])
        Item.objects.create(
            versao=versao,
            ordem=1,
            tipo="repositorio",
            dados={
                "full_name": "org/a",
                "description": "Repo A",
                "html_url": "https://github.com/org/a",
            },
        )
        resposta = self.client.get(
            reverse("admin:producao_index") + f"?conteudo={conteudo.pk}"
        )
        self.assertContains(resposta, "Itens da curadoria")
        self.assertContains(resposta, "org/a")

    def test_tela_de_falha_mostra_gerar_novamente(self):
        tarefa, _, _ = self.make_falha()
        resposta = self.client.get(
            reverse("admin:producao_index") + f"?tarefa={tarefa.pk}"
        )
        self.assertContains(resposta, "Gerar novamente")
        self.assertContains(resposta, "Geração falhou")
        self.assertNotContains(resposta, "Aprovar e publicar")

    def test_editar_cria_nova_versao(self):
        conteudo, versao = self.make_conteudo()
        resposta = self.client.post(
            reverse("admin:producao_editar", args=[conteudo.pk]),
            {
                "titulo": "Título corrigido",
                "resumo": "Resumo corrigido",
                "corpo": "# Corpo corrigido\n\nTexto revisado à mão.",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        conteudo.refresh_from_db()
        self.assertEqual(conteudo.versoes.count(), 2)
        nova = conteudo.versao_em_edicao
        self.assertNotEqual(nova.pk, versao.pk)
        self.assertEqual(nova.titulo, "Título corrigido")
        self.assertIn("Texto revisado à mão", nova.corpo)
        self.assertEqual(conteudo.estado, EstadoConteudo.RASCUNHO)
        self.assertFalse(hasattr(nova, "aprovacao"))

    def test_editar_exige_titulo(self):
        conteudo, _ = self.make_conteudo()
        self.client.post(
            reverse("admin:producao_editar", args=[conteudo.pk]),
            {"titulo": "", "resumo": "", "corpo": "texto"},
        )
        self.assertEqual(conteudo.versoes.count(), 1)

    def test_regerar_enfileira_mesma_execucao(self):
        tarefa, execucao, conteudo = self.make_falha(corpo="Texto original")
        resposta = self.client.post(
            reverse("admin:producao_regerar", args=[conteudo.pk])
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Conteudo.objects.filter(pk=conteudo.pk).exists())
        self.assertEqual(conteudo.versoes.count(), 1)
        nova = Tarefa.objects.exclude(pk=tarefa.pk).get()
        self.assertEqual(nova.parametros["execucao_id"], execucao.pk)
        self.assertEqual(nova.parametros["regerar_conteudo_id"], conteudo.pk)
        etapas = set(
            EtapaExecucao.objects.filter(execucao=execucao).values_list("nome", flat=True)
        )
        self.assertEqual(etapas, {"selecionar", "evidencias"})
        self.assertIn(f"tarefa={nova.pk}", resposta["Location"])

    def test_salvar_regeracao_cria_nova_versao_no_mesmo_conteudo(self):
        _, execucao, conteudo = self.make_falha(corpo="Texto original")
        EtapaExecucao.objects.filter(execucao=execucao, nome="salvar").delete()
        state = {
            "execucao_id": execucao.pk,
            "secao": "noticias",
            "texto": "TÍTULO: Novo título\n\nCorpo reescrito.",
            "afirmacoes": [],
            "evidencias": [],
            "imagem": {},
            "candidatos": [],
            "candidatos_deduplicados": 0,
            "fonte_resumo": "",
            "revisao": {"ok": True, "motivos": []},
            "regerar_conteudo_id": conteudo.pk,
        }
        antiga = conteudo.versao_em_edicao
        saida = motor.no_salvar(state)
        conteudo.refresh_from_db()
        self.assertEqual(saida["conteudo_id"], conteudo.pk)
        self.assertEqual(conteudo.versoes.count(), 2)
        nova = conteudo.versao_em_edicao
        self.assertEqual(nova.titulo, "Novo título")
        self.assertIn("Corpo reescrito", nova.corpo)
        self.assertEqual(nova.metadados["regerado_de"], antiga.pk)
        self.assertEqual(conteudo.estado, EstadoConteudo.AGUARDANDO_REVISAO)

    def test_tela_de_rascunho_mostra_edicao_e_regeracao(self):
        tarefa, _, _ = self.make_falha(corpo="Texto existente")
        resposta = self.client.get(
            reverse("admin:producao_index") + f"?tarefa={tarefa.pk}"
        )
        self.assertContains(resposta, "Editar texto")
        self.assertContains(resposta, "Salvar edição")
        self.assertContains(resposta, "Regerar notícia")
