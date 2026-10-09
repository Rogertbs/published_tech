import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings


class ProvedorNaoConfigurado(Exception):
    pass


class ProvedorErro(Exception):
    pass


class ProvedorTimeout(Exception):
    pass


class ProvedorIncerto(Exception):
    pass


@dataclass
class RespostaProvedor:
    texto: str
    modelo: str
    request_id: str = ""
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    tokens_cache: int | None = None
    custo_informado: Decimal | None = None
    moeda: str = "USD"


class ProvedorIA:
    nome = ""
    modelo_padrao = ""

    def gerar_texto(self, prompt: str, parametros: dict, modelo: str) -> RespostaProvedor:
        raise NotImplementedError


class MockProvedor(ProvedorIA):
    nome = "mock"
    modelo_padrao = "mock-1"

    def gerar_texto(self, prompt: str, parametros: dict, modelo: str) -> RespostaProvedor:
        return RespostaProvedor(texto=f"[simulado] {prompt[:200]}", modelo=modelo or self.modelo_padrao)


class OpenRouterProvedor(ProvedorIA):
    nome = "openrouter"

    def __init__(self, api_key=None, base_url=None, modelo_padrao=None, http_post=None):
        self.api_key = api_key or getattr(settings, "OPENROUTER_API_KEY", None)
        if not self.api_key:
            raise ProvedorNaoConfigurado("OPENROUTER_API_KEY não configurada.")
        self.base_url = (base_url or getattr(settings, "OPENROUTER_BASE_URL")).rstrip("/")
        self.modelo_padrao = modelo_padrao or getattr(settings, "AI_MODELO_PADRAO")
        self._http_post = http_post or self._post

    def gerar_texto(self, prompt: str, parametros: dict, modelo: str) -> RespostaProvedor:
        modelo = modelo or self.modelo_padrao
        corpo = {"model": modelo, "messages": [{"role": "user", "content": prompt}]}
        corpo.update(parametros or {})
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://published.tech",
            "X-Title": "Published Tech",
        }
        url = f"{self.base_url}/chat/completions"
        status, _, body = self._http_post(url, headers, json.dumps(corpo))

        if status in (408, 504):
            raise ProvedorTimeout(f"OpenRouter respondeu HTTP {status}.")
        if status >= 500:
            raise ProvedorIncerto(f"OpenRouter respondeu HTTP {status} (resultado incerto).")
        if status >= 400:
            raise ProvedorErro(f"OpenRouter respondeu HTTP {status}.")

        try:
            payload = json.loads(body)
            texto = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise ProvedorErro(f"Resposta inesperada do OpenRouter: {exc}") from exc

        usage = payload.get("usage") or {}
        custo = usage.get("cost", usage.get("total_cost"))
        cache = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        return RespostaProvedor(
            texto=texto,
            modelo=payload.get("model") or modelo,
            request_id=payload.get("id") or "",
            tokens_entrada=usage.get("prompt_tokens"),
            tokens_saida=usage.get("completion_tokens"),
            tokens_cache=cache,
            custo_informado=Decimal(str(custo)) if custo is not None else None,
        )

    def _post(self, url: str, headers: dict, body: str):
        request = urllib.request.Request(url, data=body.encode(), headers=headers, method="POST")
        timeout = float(getattr(settings, "AI_TIMEOUT_SECONDS", 30))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read().decode()
        except (TimeoutError, socket.timeout) as exc:
            raise ProvedorTimeout(str(exc)) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProvedorTimeout(str(exc)) from exc
            raise ProvedorIncerto(str(exc)) from exc
        except OSError as exc:
            raise ProvedorIncerto(str(exc)) from exc


def obter_provedor() -> ProvedorIA:
    nome = getattr(settings, "AI_PROVIDER", "mock")
    if nome == "openrouter":
        return OpenRouterProvedor()
    if nome == "mock":
        return MockProvedor()
    raise ProvedorNaoConfigurado(f"Provedor de IA '{nome}' desconhecido.")
