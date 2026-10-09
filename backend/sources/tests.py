import json
import os
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from sources import services
from sources.models import (
    Candidato,
    CategoriaModelo,
    Coleta,
    EstadoColeta,
    Fonte,
    RegistroNormalizado,
    TipoFonte,
)


def item(repo_id, full_name, estrelas, pushed="2026-10-08T00:00:00Z"):
    return {
        "id": repo_id,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "description": "desc",
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "stargazers_count": estrelas,
        "forks_count": 3,
        "open_issues_count": 1,
        "created_at": "2026-10-01T00:00:00Z",
        "pushed_at": pushed,
    }


def get_ok(items, capturado=None):
    def _get(url, headers):
        if capturado is not None:
            capturado.append((url, headers))
        return 200, {}, json.dumps({"items": items})

    return _get


class ColetaTests(TestCase):
    def fonte(self, nome="GitHub Destaques", **kwargs):
        defaults = dict(tipo=TipoFonte.GITHUB, parametros={"min_estrelas": 10, "selecao": 5})
        defaults.update(kwargs)
        return Fonte.objects.create(nome=nome, **defaults)

    def test_coletar_cria_registros_e_candidatos(self):
        fonte = self.fonte()
        itens = [item(1, "a/b", 100), item(2, "c/d", 50)]

        coleta = services.coletar(fonte, http_get=get_ok(itens), sleep=lambda s: None)

        self.assertEqual(coleta.estado, EstadoColeta.OK)
        self.assertEqual(coleta.total_registros, 2)
        self.assertEqual(RegistroNormalizado.objects.filter(fonte=fonte).count(), 2)
        self.assertEqual(Candidato.objects.count(), 2)
        self.assertTrue(all(c.motivo for c in Candidato.objects.all()))

    def test_deduplicacao_por_chave_externa(self):
        fonte = self.fonte()
        itens = [item(1, "a/b", 100)]
        services.coletar(fonte, http_get=get_ok(itens), sleep=lambda s: None)
        services.coletar(fonte, http_get=get_ok(itens), sleep=lambda s: None)
        self.assertEqual(RegistroNormalizado.objects.filter(fonte=fonte).count(), 1)

    def test_fonte_desabilitada_nao_coleta_e_preserva_historico(self):
        fonte = self.fonte()
        services.coletar(fonte, http_get=get_ok([item(1, "a/b", 100)]), sleep=lambda s: None)
        fonte.habilitada = False
        fonte.save(update_fields=["habilitada"])

        resultado = services.coletar_todas(http_get=get_ok([item(2, "c/d", 9)]), sleep=lambda s: None)

        self.assertEqual(resultado["coletas"], [])
        self.assertEqual(resultado["estado"], EstadoColeta.OK)
        self.assertEqual(RegistroNormalizado.objects.filter(fonte=fonte).count(), 1)

    def test_coletar_fonte_desabilitada_levanta(self):
        fonte = self.fonte(habilitada=False)
        with self.assertRaises(services.FonteDesabilitada):
            services.coletar(fonte, http_get=get_ok([]), sleep=lambda s: None)
        self.assertEqual(RegistroNormalizado.objects.count(), 0)

    def test_todas_falharem_estado_falhou(self):
        self.fonte(nome="A", parametros={"min_estrelas": 1})
        self.fonte(nome="B", parametros={"min_estrelas": 2})

        def http_get(url, headers):
            return 500, {}, "erro"

        resultado = services.coletar_todas(http_get=http_get, sleep=lambda s: None)
        self.assertEqual(resultado["estado"], EstadoColeta.FALHOU)

    def test_rate_limit_com_retry_volta_a_ok(self):
        fonte = self.fonte()
        itens = [item(1, "a/b", 100)]
        atrasos = []
        respostas = iter(
            [
                (403, {"X-RateLimit-Remaining": "0"}, "{}"),
                (200, {}, json.dumps({"items": itens})),
            ]
        )

        def http_get(url, headers):
            return next(respostas)

        coleta = services.coletar(fonte, http_get=http_get, sleep=atrasos.append)

        self.assertEqual(coleta.estado, EstadoColeta.OK)
        self.assertEqual(len(atrasos), 1)
        self.assertGreaterEqual(atrasos[0], 1)

    def test_rate_limit_persistente_falha_parcial(self):
        fonte = self.fonte()

        def http_get(url, headers):
            return 429, {"Retry-After": "1"}, "{}"

        coleta = services.coletar(fonte, http_get=http_get, sleep=lambda s: None)
        self.assertEqual(coleta.estado, EstadoColeta.FALHOU_PARCIAL)
        self.assertIn("Limite", coleta.erro)

    def test_erro_de_servidor_falha(self):
        fonte = self.fonte()

        def http_get(url, headers):
            return 500, {}, "erro"

        coleta = services.coletar(fonte, http_get=http_get, sleep=lambda s: None)
        self.assertEqual(coleta.estado, EstadoColeta.FALHOU)

    def test_falha_de_uma_fonte_nao_derruba_outra(self):
        boa = self.fonte(nome="Boa", parametros={"min_estrelas": 1})
        ruim = self.fonte(nome="Ruim", parametros={"min_estrelas": 999})

        def http_get(url, headers):
            if "999" in url:
                return 500, {}, "erro"
            return 200, {}, json.dumps({"items": [item(1, "a/b", 100)]})

        resultado = services.coletar_todas(http_get=http_get, sleep=lambda s: None)

        self.assertEqual(resultado["estado"], EstadoColeta.FALHOU_PARCIAL)
        estados = {c.fonte_id: c.estado for c in resultado["coletas"]}
        self.assertEqual(estados[boa.pk], EstadoColeta.OK)
        self.assertEqual(estados[ruim.pk], EstadoColeta.FALHOU)

    def test_token_vai_no_header(self):
        fonte = self.fonte(credencial_ref="TESTE_GITHUB_TOKEN")
        os.environ["TESTE_GITHUB_TOKEN"] = "segredo123"
        capturado = []
        try:
            services.coletar(fonte, http_get=get_ok([item(1, "a/b", 1)], capturado), sleep=lambda s: None)
        finally:
            del os.environ["TESTE_GITHUB_TOKEN"]
        _, headers = capturado[0]
        self.assertEqual(headers["Authorization"], "Bearer segredo123")
        self.assertEqual(headers["X-GitHub-Api-Version"], "2026-03-10")

    def test_selecao_ordena_e_limita(self):
        fonte = self.fonte()
        itens = [item(1, "a/b", 10), item(2, "c/d", 900), item(3, "e/f", 500)]
        coleta = services.coletar(fonte, http_get=get_ok(itens), sleep=lambda s: None)

        candidatos = services.selecionar_candidatos(coleta, limite=2)

        self.assertEqual(len(candidatos), 2)
        self.assertEqual(candidatos[0].registro.chave_externa, "2")
        self.assertEqual(candidatos[1].registro.chave_externa, "3")
        self.assertTrue(candidatos[0].motivo)
        self.assertEqual(Coleta.objects.get(pk=coleta.pk).estado, EstadoColeta.OK)


def hf_item(mid, trending=0, created=None, tags=None, pipeline="text-generation", gated=False, **extra):
    dados = {
        "id": mid,
        "author": mid.split("/")[0],
        "pipeline_tag": pipeline,
        "library_name": "transformers",
        "downloads": extra.pop("downloads", 0),
        "likes": extra.pop("likes", 0),
        "trendingScore": trending,
        "createdAt": created or timezone.now().isoformat(),
        "lastModified": timezone.now().isoformat(),
        "tags": tags or [],
        "gated": gated,
    }
    dados.update(extra)
    return dados


def get_lista(models, capturado=None):
    def _get(url, headers):
        if capturado is not None:
            capturado.append((url, headers))
        return 200, {}, json.dumps(models)

    return _get


class HuggingFaceTests(TestCase):
    def fonte(self, **kwargs):
        defaults = dict(tipo=TipoFonte.HUGGINGFACE, parametros={"limite": 30, "selecao": 5})
        defaults.update(kwargs)
        return Fonte.objects.create(nome="HF Radar", **defaults)

    def test_agrupa_variantes_da_mesma_familia(self):
        models = [
            hf_item("org/model", trending=100, tags=["license:apache-2.0", "safetensors"]),
            hf_item("org/model-GGUF", trending=500, tags=["base_model:org/model", "license:apache-2.0", "gguf"]),
        ]
        registros = services.obter_conector(self.fonte()).listar(
            {"limite": 30}, None, http_get=get_lista(models), sleep=lambda s: None
        )
        self.assertEqual(len(registros), 1)
        dados = registros[0]["dados"]
        self.assertEqual(dados["id"], "org/model-GGUF")
        self.assertEqual(sorted(dados["variantes"]), ["org/model", "org/model-GGUF"])
        self.assertEqual(dados["categoria"], CategoriaModelo.NOVA_VARIANTE)

    def test_categorias(self):
        antigo = (timezone.now() - timedelta(days=400)).isoformat()
        models = [
            hf_item("org/base", trending=10),
            hf_item("org/variante", trending=200, tags=["base_model:org/base"]),
            hf_item("org/antigo", trending=1000, created=antigo),
            hf_item("org/novo", trending=5),
        ]
        registros = services.obter_conector(self.fonte()).listar(
            {"limite": 30}, None, http_get=get_lista(models), sleep=lambda s: None
        )
        por_id = {r["dados"]["id"]: r["dados"]["categoria"] for r in registros}
        self.assertNotIn("org/base", por_id)
        self.assertEqual(por_id["org/variante"], CategoriaModelo.NOVA_VARIANTE)
        self.assertEqual(por_id["org/antigo"], CategoriaModelo.MODELO_ANTIGO_ATENCAO)
        self.assertEqual(por_id["org/novo"], CategoriaModelo.ATUALIZACAO_REPOSITORIO)

    def test_nao_usa_created_at_como_lancamento(self):
        models = [hf_item("org/novo", trending=100)]
        registro = services.obter_conector(self.fonte()).listar(
            {"limite": 30}, None, http_get=get_lista(models), sleep=lambda s: None
        )[0]["dados"]
        self.assertFalse(registro["lancamento_confirmado"])
        self.assertNotEqual(registro["categoria"], CategoriaModelo.LANCAMENTO_CONFIRMADO)
        self.assertEqual(registro["data_lancamento"], "Desconhecido")

    def test_campos_ausentes_ficam_desconhecidos(self):
        models = [hf_item("org/x", trending=1)]
        dados = services.obter_conector(self.fonte()).listar(
            {"limite": 30}, None, http_get=get_lista(models), sleep=lambda s: None
        )[0]["dados"]
        self.assertEqual(dados["licenca"], "Desconhecido")
        self.assertEqual(dados["parametros"], "Desconhecido")
        self.assertEqual(dados["base_model"], "Desconhecido")
        self.assertEqual(dados["anuncio"], "Desconhecido")
        self.assertFalse(dados["acesso_restrito"])

    def test_coleta_hf_via_service(self):
        fonte = self.fonte()
        models = [hf_item("org/a", trending=100, tags=["license:mit"]), hf_item("org/b", trending=50)]
        coleta = services.coletar(fonte, http_get=get_lista(models), sleep=lambda s: None)
        self.assertEqual(coleta.estado, EstadoColeta.OK)
        self.assertEqual(RegistroNormalizado.objects.filter(fonte=fonte).count(), 2)
        self.assertEqual(Candidato.objects.count(), 2)

    def test_acesso_restrito(self):
        models = [hf_item("org/gated", trending=5, gated="auto", tags=["license:apache-2.0"])]
        dados = services.obter_conector(self.fonte()).listar(
            {"limite": 30}, None, http_get=get_lista(models), sleep=lambda s: None
        )[0]["dados"]
        self.assertTrue(dados["acesso_restrito"])
