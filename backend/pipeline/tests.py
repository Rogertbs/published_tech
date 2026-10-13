from unittest import mock

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ai.models import ChamadaIA
from configuracao import services as cfg
from configuracao.models import Configuracao, EscopoConfig
from content.models import Conteudo, EstadoConteudo, Versao
from pipeline import motor
from pipeline.models import EstadoExecucao, EtapaExecucao, Evidencia, Execucao
from pipeline.services import produzir_curadoria, produzir_noticia
from sources.models import Candidato, Fonte, RegistroNormalizado, TipoFonte
from tests.factories import get_feed, gh_get, repo


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


def seed_hf(registros):
    fonte = Fonte.objects.create(nome="HF", tipo=TipoFonte.HUGGINGFACE, parametros={"selecao": 5})
    for item in registros:
        registro = RegistroNormalizado.objects.create(
            fonte=fonte, chave_externa=item["id"], dados=item, coletado_em=timezone.now()
        )
        Candidato.objects.create(registro=registro, pontuacao=item.get("trendingScore", 0), selecionado=True)
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
        self.assertIsNotNone(get_handler("noticia"))
        self.assertIsNotNone(get_handler("curadoria"))


class NoticiaTests(TestCase):
    def test_produzir_noticia_gera_rascunho(self):
        fonte = Fonte.objects.create(
            nome="RSS",
            tipo=TipoFonte.RSS,
            parametros={"feed_url": "https://exemplo.com/feed", "selecao": 1},
        )
        resultado = produzir_noticia(fonte=fonte, http_get=get_feed(), sleep=lambda s: None)

        self.assertEqual(resultado["coleta"], "ok")
        self.assertEqual(resultado["estado_conteudo"], "aguardando_revisao")
        conteudo = Conteudo.objects.get(slug=resultado["conteudo"])
        self.assertEqual(conteudo.secao, "noticias")
        self.assertEqual(conteudo.tipo, "artigo")
        self.assertTrue(conteudo.versao_em_edicao.metadados["fontes"])
        self.assertTrue(resultado["texto"])
        self.assertIn("português do Brasil", resultado["texto"])

    def test_endpoint_noticias_enfileira_e_e_idempotente(self):
        from jobs.models import Tarefa

        payload = '{"chave_idempotencia": "k1"}'
        primeira = self.client.post("/api/noticias", payload, content_type="application/json")
        self.assertEqual(primeira.status_code, 202)
        self.assertTrue(Tarefa.objects.filter(tipo_tarefa="noticia", chave_idempotencia="k1").exists())

        segunda = self.client.post("/api/noticias", payload, content_type="application/json")
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(Tarefa.objects.filter(tipo_tarefa="noticia").count(), 1)

    def test_endpoint_noticias_pausado(self):
        from jobs import services as jobs

        jobs.pausar()
        resposta = self.client.post("/api/noticias", "{}", content_type="application/json")
        self.assertEqual(resposta.status_code, 409)


class CuradoriaTests(TestCase):
    def test_produzir_curadoria(self):
        fonte = Fonte.objects.create(nome="GH", tipo=TipoFonte.GITHUB, parametros={"selecao": 2})
        resultado = produzir_curadoria(
            "destaques-github",
            fonte=fonte,
            http_get=gh_get([repo(1, "org/a", 100), repo(2, "org/b", 50)]),
            sleep=lambda s: None,
        )
        self.assertEqual(resultado["coleta"], "ok")
        self.assertEqual(resultado["itens"], 2)
        conteudo = Conteudo.objects.get(slug=resultado["conteudo"])
        self.assertEqual(conteudo.secao, "destaques-github")

    def test_endpoint_curadorias_enfileira(self):
        from jobs.models import Tarefa

        resposta = self.client.post(
            "/api/curadorias",
            '{"secao": "radar-hf", "chave_idempotencia": "c1"}',
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 202)
        self.assertTrue(Tarefa.objects.filter(tipo_tarefa="curadoria", chave_idempotencia="c1").exists())

    def test_endpoint_curadorias_secao_invalida(self):
        resposta = self.client.post(
            "/api/curadorias", '{"secao": "x"}', content_type="application/json"
        )
        self.assertEqual(resposta.status_code, 400)

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

    def test_curadoria_hugging_face(self):
        seed_hf(
            [
                {"id": "org/model", "url": "https://huggingface.co/org/model", "resumo": "m", "trendingScore": 100}
            ]
        )
        motor.executar_pipeline(secao="radar-hf")

        versao = Versao.objects.get()
        self.assertEqual(versao.itens.get().tipo, "modelo")
        self.assertIn("Curadoria própria", versao.metadados["aviso_curadoria"])
        self.assertIn("Coleta em", versao.metadados["aviso_curadoria"])

    def test_custo_por_postagem(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        motor.executar_pipeline(secao="destaques-github")
        conteudo = Conteudo.objects.get()
        self.assertEqual(ChamadaIA.objects.get().conteudo_id, conteudo.pk)


def seed_rss(registros):
    fonte = Fonte.objects.create(nome="RSS", tipo=TipoFonte.RSS, parametros={"selecao": 1})
    for item in registros:
        registro = RegistroNormalizado.objects.create(
            fonte=fonte,
            chave_externa=item["url"],
            dados=item,
            coletado_em=timezone.now(),
        )
        Candidato.objects.create(
            registro=registro, pontuacao=item.get("pontuacao", 0), selecionado=True
        )
    return fonte


class DeduplicacaoTests(TestCase):
    def test_nao_duplica_mesma_origem(self):
        seed_github([dados("1", "org/a", estrelas=500)])

        primeira = motor.executar_pipeline(secao="destaques-github")
        self.assertEqual(Conteudo.objects.count(), 1)
        self.assertIsNotNone(RegistroNormalizado.objects.get().usado_em)

        segunda = motor.executar_pipeline(secao="destaques-github")
        self.assertEqual(primeira.estado, EstadoExecucao.CONCLUIDA)
        self.assertEqual(Conteudo.objects.count(), 1)
        self.assertIn("conteudo_duplicado", segunda.motivo)

    def test_origem_nova_gera_conteudo_novo(self):
        seed_rss(
            [
                {"url": "https://exemplo.com/a", "full_name": "A", "resumo": "a", "pontuacao": 10},
                {"url": "https://exemplo.com/b", "full_name": "B", "resumo": "b", "pontuacao": 5},
            ]
        )

        motor.executar_pipeline(secao="noticias")
        motor.executar_pipeline(secao="noticias")

        self.assertEqual(Conteudo.objects.count(), 2)
        usados = set(RegistroNormalizado.objects.values_list("chave_externa", flat=True))
        self.assertEqual(usados, {"https://exemplo.com/a", "https://exemplo.com/b"})

    def test_marca_origem_como_usada(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        motor.executar_pipeline(secao="destaques-github")
        self.assertTrue(RegistroNormalizado.objects.get().usado_em)

    def test_deduplicacao_desligada_permite_reprocessar(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        geral = Configuracao.objects.create(chave="geral", escopo=EscopoConfig.GERAL)
        cfg.criar_versao(geral, {"deduplicar_itens": False}, ativar=True)

        motor.executar_pipeline(secao="destaques-github")
        motor.executar_pipeline(secao="destaques-github")

        self.assertEqual(Conteudo.objects.count(), 2)

    def test_janela_deduplicacao_permite_reuso(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        geral = Configuracao.objects.create(chave="geral", escopo=EscopoConfig.GERAL)
        cfg.criar_versao(geral, {"deduplicacao_janela_dias": 1}, ativar=True)

        motor.executar_pipeline(secao="destaques-github")
        antigo = timezone.now() - timedelta(days=3)
        RegistroNormalizado.objects.update(usado_em=antigo)
        Versao.objects.update(criado_em=antigo)

        motor.executar_pipeline(secao="destaques-github")

        self.assertEqual(Conteudo.objects.count(), 2)

    def test_janela_zero_permite_reuso_imediato(self):
        seed_github([dados("1", "org/a", estrelas=500)])
        geral = Configuracao.objects.create(chave="geral", escopo=EscopoConfig.GERAL)
        cfg.criar_versao(geral, {"deduplicacao_janela_dias": 0}, ativar=True)

        motor.executar_pipeline(secao="destaques-github")
        motor.executar_pipeline(secao="destaques-github")

        self.assertEqual(Conteudo.objects.count(), 2)

    def test_deduplicacao_registra_auditoria(self):
        from auditoria.models import AuditoriaAdministrativa

        seed_github([dados("1", "org/a", estrelas=500)])
        motor.executar_pipeline(secao="destaques-github")
        motor.executar_pipeline(secao="destaques-github")

        self.assertTrue(AuditoriaAdministrativa.objects.filter(acao="deduplicacao").exists())
