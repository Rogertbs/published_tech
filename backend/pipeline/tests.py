from unittest import mock

from django.test import TestCase
from django.utils import timezone

from ai.models import ChamadaIA
from configuracao import services as cfg
from configuracao.models import Configuracao, EscopoConfig
from content.models import Conteudo, EstadoConteudo, Versao
from pipeline import motor
from pipeline.models import EstadoExecucao, EtapaExecucao, Evidencia, Execucao
from sources.models import Candidato, Fonte, RegistroNormalizado, TipoFonte


def dados(id_, full_name, licenca="MIT", descricao="desc", estrelas=100):
    return {
        "id": id_,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "description": descricao,
        "licenca": licenca,
        "estrelas": estrelas,
    }


def seed_github(registros):
    fonte = Fonte.objects.create(nome="GitHub", tipo=TipoFonte.GITHUB, parametros={"selecao": 5})
    for item in registros:
        registro = RegistroNormalizado.objects.create(
            fonte=fonte, chave_externa=item["id"], dados=item, coletado_em=timezone.now()
        )
        Candidato.objects.create(registro=registro, pontuacao=item.get("estrelas", 0), selecionado=True)
    return fonte


class PipelineTests(TestCase):
    def test_gera_rascunho_com_evidencias(self):
        seed_github([dados("1", "org/a", estrelas=500), dados("2", "org/b", estrelas=100)])

        execucao = motor.executar_pipeline(secao="destaques-github")

        self.assertEqual(execucao.estado, EstadoExecucao.CONCLUIDA)
        conteudo = Conteudo.objects.get()
        self.assertEqual(conteudo.estado, EstadoConteudo.AGUARDANDO_REVISAO)
        versao = Versao.objects.get()
        self.assertEqual(conteudo.versao_em_edicao_id, versao.pk)
        self.assertTrue(versao.corpo)
        self.assertEqual(Evidencia.objects.filter(versao=versao).count(), 2)
        self.assertEqual(ChamadaIA.objects.filter(finalidade="redacao").count(), 1)
        self.assertEqual(ChamadaIA.objects.get().execucao_id, execucao.pk)

    def test_sem_candidatos_retem_rascunho(self):
        execucao = motor.executar_pipeline(secao="destaques-github")

        self.assertEqual(Conteudo.objects.get().estado, EstadoConteudo.RASCUNHO)
        self.assertIn("evidencia_insuficiente", execucao.motivo)

    def test_afirmacao_sem_evidencia_retem(self):
        sem_fonte = {"id": "9", "full_name": "org/vazio", "html_url": "", "description": "", "licenca": "MIT"}
        seed_github([sem_fonte])
        execucao = motor.executar_pipeline(secao="destaques-github")

        self.assertEqual(Conteudo.objects.get().estado, EstadoConteudo.RASCUNHO)
        self.assertIn("evidencia_insuficiente", execucao.motivo)
        self.assertEqual(Evidencia.objects.count(), 0)

    def test_contradicao_nao_resolvida(self):
        seed_github(
            [
                dados("1", "org/x", licenca="MIT", descricao="a"),
                dados("2", "org/x", licenca="GPL", descricao="b"),
            ]
        )
        execucao = motor.executar_pipeline(secao="destaques-github")

        self.assertEqual(Conteudo.objects.get().estado, EstadoConteudo.RASCUNHO)
        self.assertIn("contradicao_factual", execucao.motivo)
        self.assertEqual(Versao.objects.get().metadados["imagem"], {})

    def test_avaliar_revisao_afirmacao_sem_evidencia(self):
        resultado = motor.avaliar_revisao([{"texto": "x", "evidencia_ids": []}], False)
        self.assertFalse(resultado["ok"])
        self.assertIn("evidencia_insuficiente", resultado["motivos"])

    def test_retomavel_sem_reexecutar_etapas(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        execucao = motor.executar_pipeline(secao="destaques-github")
        versao_id = Versao.objects.get().pk
        chamadas = ChamadaIA.objects.count()
        evidencias = Evidencia.objects.count()

        motor.executar_pipeline(secao="destaques-github", execucao=execucao)

        self.assertEqual(Versao.objects.get().pk, versao_id)
        self.assertEqual(ChamadaIA.objects.count(), chamadas)
        self.assertEqual(Evidencia.objects.count(), evidencias)
        self.assertEqual(EtapaExecucao.objects.filter(execucao=execucao).count(), 6)

    def test_retomavel_apos_falha(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        original = motor.avaliar_revisao
        estado = {"n": 0}

        def falha_uma_vez(*args, **kwargs):
            estado["n"] += 1
            if estado["n"] == 1:
                raise RuntimeError("queda")
            return original(*args, **kwargs)

        with mock.patch("pipeline.motor.avaliar_revisao", side_effect=falha_uma_vez):
            execucao = motor.executar_pipeline(secao="destaques-github")
        self.assertEqual(execucao.estado, EstadoExecucao.FALHOU)
        chamadas = ChamadaIA.objects.count()

        retomada = motor.executar_pipeline(secao="destaques-github", execucao=execucao)
        self.assertEqual(retomada.estado, EstadoExecucao.CONCLUIDA)
        self.assertEqual(ChamadaIA.objects.count(), chamadas)
        self.assertTrue(EtapaExecucao.objects.filter(execucao=execucao, nome="revisar").exists())

    def test_falha_de_imagem_gera_rascunho_sem_imagem(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        with mock.patch("pipeline.motor.gerar_ilustracao", side_effect=RuntimeError("sem GPU")):
            motor.executar_pipeline(secao="destaques-github")

        versao = Versao.objects.get()
        self.assertTrue(versao.metadados["imagem"]["ausente"])
        self.assertEqual(Conteudo.objects.get().estado, EstadoConteudo.AGUARDANDO_REVISAO)

    def test_imagem_mocada_placeholder(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        motor.executar_pipeline(secao="destaques-github")
        imagem = Versao.objects.get().metadados["imagem"]
        self.assertTrue(imagem["mocada"])
        self.assertIn("Ilustração gerada por IA", imagem["legenda"])

    def test_handlers_registrados(self):
        from jobs.handlers import get_handler

        self.assertIsNotNone(get_handler("pipeline"))
        self.assertIsNotNone(get_handler("coletar"))

    def test_itens_estruturados_e_aviso(self):
        seed_github([dados("1", "org/a", estrelas=500), dados("2", "org/b", estrelas=100)])
        motor.executar_pipeline(secao="destaques-github")

        versao = Versao.objects.get()
        self.assertEqual(versao.itens.count(), 2)
        item = versao.itens.first()
        self.assertEqual(item.tipo, "repositorio")
        self.assertEqual(item.dados["full_name"], "org/a")
        self.assertIn("Curadoria própria", versao.metadados["aviso_curadoria"])

    def test_quantidade_itens_configuravel(self):
        seed_github([dados(str(i), f"org/{i}", estrelas=100 * i) for i in range(1, 5)])
        geral = Configuracao.objects.create(chave="geral", escopo=EscopoConfig.GERAL)
        cfg.criar_versao(geral, {"quantidade_itens": 3}, ativar=True)

        motor.executar_pipeline(secao="destaques-github")
        self.assertEqual(Versao.objects.get().itens.count(), 3)
