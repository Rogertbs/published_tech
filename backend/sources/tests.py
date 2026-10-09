import json
import os

from django.test import TestCase

from sources import services
from sources.models import Coleta, EstadoColeta, Fonte, RegistroNormalizado, TipoFonte


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

    def test_coletar_cria_registros(self):
        fonte = self.fonte()
        itens = [item(1, "a/b", 100), item(2, "c/d", 50)]

        coleta = services.coletar(fonte, http_get=get_ok(itens), sleep=lambda s: None)

        self.assertEqual(coleta.estado, EstadoColeta.OK)
        self.assertEqual(coleta.total_registros, 2)
        self.assertEqual(RegistroNormalizado.objects.filter(fonte=fonte).count(), 2)

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
