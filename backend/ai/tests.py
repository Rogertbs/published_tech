import json
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from ai import instrumentation
from ai.models import ChamadaIA, OrigemCusto, PrecoModelo, StatusChamada
from ai.providers import MockProvedor, OpenRouterProvedor, ProvedorIncerto, ProvedorNaoConfigurado, ProvedorTimeout


def or_post(payload, status=200):
    def _post(url, headers, body):
        return status, {}, json.dumps(payload)

    return _post


def payload_openrouter(cost=0.00012, prompt_tokens=10, completion_tokens=5):
    usage = {}
    if prompt_tokens is not None:
        usage["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        usage["completion_tokens"] = completion_tokens
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "choices": [{"message": {"content": "olá"}}],
        "usage": usage,
    }


def provedor_openrouter(payload=None, status=200, http_post=None):
    return OpenRouterProvedor(
        api_key="chave-secreta",
        base_url="https://openrouter.ai/api/v1",
        modelo_padrao="meta-llama/llama-3.3-70b-instruct:free",
        http_post=http_post or or_post(payload or payload_openrouter(), status),
    )


class InstrumentacaoTests(TestCase):
    def test_mock_registra_desconhecido(self):
        resposta = instrumentation.executar_texto("escreva", finalidade="redacao", provedor=MockProvedor())
        chamada = resposta.chamada
        self.assertEqual(chamada.status, StatusChamada.SUCESSO)
        self.assertEqual(chamada.provedor, "mock")
        self.assertIn("simulado", resposta.texto)
        self.assertIsNone(chamada.tokens_entrada)
        self.assertIsNone(chamada.custo)
        self.assertEqual(chamada.origem_custo, OrigemCusto.DESCONHECIDO)

    def test_openrouter_custo_informado(self):
        chamada = instrumentation.executar_texto(
            "escreva", finalidade="redacao", provedor=provedor_openrouter()
        ).chamada
        self.assertEqual(chamada.status, StatusChamada.SUCESSO)
        self.assertEqual(chamada.tokens_entrada, 10)
        self.assertEqual(chamada.tokens_saida, 5)
        self.assertEqual(chamada.custo, Decimal("0.00012"))
        self.assertEqual(chamada.origem_custo, OrigemCusto.INFORMADO)
        self.assertEqual(chamada.request_id_externo, "gen-1")

    def test_timeout(self):
        def http_post(url, headers, body):
            raise ProvedorTimeout("demorou")

        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter(http_post=http_post)
        ).chamada
        self.assertEqual(chamada.status, StatusChamada.TIMEOUT)
        self.assertIsNone(chamada.custo)
        self.assertEqual(chamada.origem_custo, OrigemCusto.DESCONHECIDO)

    def test_incerto(self):
        def http_post(url, headers, body):
            raise ProvedorIncerto("conexão caiu após envio")

        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter(http_post=http_post)
        ).chamada
        self.assertEqual(chamada.status, StatusChamada.INCERTO)

    def test_erro_http_definitivo(self):
        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter(payload={}, status=400)
        ).chamada
        self.assertEqual(chamada.status, StatusChamada.ERRO)

    def test_200_json_invalido_incerto(self):
        def http_post(url, headers, body):
            return 200, {}, "não é json"

        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter(http_post=http_post)
        ).chamada
        self.assertEqual(chamada.status, StatusChamada.INCERTO)

    def test_http_5xx_incerto(self):
        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter(payload={}, status=503)
        ).chamada
        self.assertEqual(chamada.status, StatusChamada.INCERTO)

    def test_custo_estimado_com_tabela_de_preco(self):
        PrecoModelo.objects.create(
            provedor="openrouter",
            modelo="meta-llama/llama-3.3-70b-instruct:free",
            moeda="USD",
            preco_entrada_por_milhao=Decimal("1.0"),
            preco_saida_por_milhao=Decimal("2.0"),
            vigente_de=timezone.now(),
        )
        payload = payload_openrouter(cost=None, prompt_tokens=1_000_000, completion_tokens=500_000)
        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter(payload=payload)
        ).chamada
        self.assertEqual(chamada.origem_custo, OrigemCusto.ESTIMADO)
        self.assertEqual(chamada.custo, Decimal("2.000000"))
        self.assertEqual(chamada.preco_aplicado, Decimal("2.0"))

    def test_moeda_estimada_vem_do_preco(self):
        PrecoModelo.objects.create(
            provedor="openrouter",
            modelo="meta-llama/llama-3.3-70b-instruct:free",
            moeda="BRL",
            preco_entrada_por_milhao=Decimal("1.0"),
            preco_saida_por_milhao=Decimal("1.0"),
            vigente_de=timezone.now(),
        )
        payload = payload_openrouter(cost=None, prompt_tokens=1000, completion_tokens=1000)
        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter(payload=payload)
        ).chamada
        self.assertEqual(chamada.origem_custo, OrigemCusto.ESTIMADO)
        self.assertEqual(chamada.moeda, "BRL")

    def test_tokens_desconhecidos_nao_sao_zero(self):
        payload = payload_openrouter(cost=None, prompt_tokens=None, completion_tokens=None)
        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter(payload=payload)
        ).chamada
        self.assertIsNone(chamada.tokens_entrada)
        self.assertIsNone(chamada.tokens_saida)
        self.assertIsNone(chamada.custo)
        self.assertEqual(chamada.origem_custo, OrigemCusto.DESCONHECIDO)

    @override_settings(AI_PROVIDER="openrouter", OPENROUTER_API_KEY=None)
    def test_sem_chave_levanta_e_nao_faz_fallback(self):
        with self.assertRaises(ProvedorNaoConfigurado):
            instrumentation.executar_texto("x", finalidade="redacao")
        self.assertEqual(ChamadaIA.objects.count(), 0)

    def test_credencial_nao_e_registrada(self):
        chamada = instrumentation.executar_texto(
            "x", finalidade="redacao", provedor=provedor_openrouter()
        ).chamada
        campos = [str(v) for v in chamada.__dict__.values()]
        self.assertFalse(any("chave-secreta" in valor for valor in campos))

    def test_correlacao_registrada(self):
        chamada = instrumentation.executar_texto(
            "x",
            finalidade="revisao",
            etapa="revisar",
            conteudo_id=42,
            correlacao={"run": "abc"},
            provedor=MockProvedor(),
        ).chamada
        self.assertEqual(chamada.finalidade, "revisao")
        self.assertEqual(chamada.etapa, "revisar")
        self.assertEqual(chamada.conteudo_id, 42)
        self.assertEqual(chamada.correlacao, {"run": "abc"})
