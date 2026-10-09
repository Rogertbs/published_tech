import json
import time
import urllib.error
import urllib.request
from datetime import timedelta

from django.utils import timezone

from sources.connectors.base import (
    Conector,
    ConectorError,
    ConectorIndisponivel,
    RateLimitPersistente,
)

API_URL = "https://api.github.com/search/repositories"
API_VERSION = "2026-03-10"


def urllib_get(url: str, headers: dict, timeout: int = 10):
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConectorIndisponivel(str(exc)) from exc


class GitHubConector(Conector):
    tipo = "github"

    def listar(self, parametros: dict, token: str | None, *, http_get=urllib_get, sleep=time.sleep):
        parametros = parametros or {}
        janela = int(parametros.get("janela_dias", 7))
        min_estrelas = int(parametros.get("min_estrelas", 0))
        limite = max(1, min(int(parametros.get("limite", 20)), 100))
        desde = (timezone.now() - timedelta(days=janela)).date().isoformat()

        qualificadores = [f"stars:>={min_estrelas}", f"pushed:>={desde}"]
        if parametros.get("language"):
            qualificadores.append(f"language:{parametros['language']}")
        if parametros.get("topic"):
            qualificadores.append(f"topic:{parametros['topic']}")
        url = f"{API_URL}?q={'+'.join(qualificadores)}&sort=stars&order=desc&per_page={limite}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "published-tech",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        status, headers_resposta, corpo = self._requisitar(url, headers, http_get, sleep)
        payload = json.loads(corpo or "{}")
        agora = timezone.now()
        return [self._normalizar(item, agora) for item in payload.get("items", [])]

    def _requisitar(self, url, headers, http_get, sleep, max_tentativas=3):
        for tentativa in range(1, max_tentativas + 1):
            status, headers_resposta, corpo = http_get(url, headers)
            limite_atingido = status == 429 or (
                status == 403 and headers_resposta.get("X-RateLimit-Remaining") == "0"
            )
            if limite_atingido:
                if tentativa >= max_tentativas:
                    raise RateLimitPersistente("Limite de taxa do GitHub atingido.")
                sleep(self._atraso(headers_resposta, tentativa))
                continue
            if status >= 500:
                if tentativa >= max_tentativas:
                    raise ConectorIndisponivel(f"GitHub respondeu HTTP {status}.")
                sleep(2 ** tentativa)
                continue
            if status >= 400:
                raise ConectorError(f"GitHub respondeu HTTP {status}.")
            return status, headers_resposta, corpo
        raise ConectorIndisponivel("Não foi possível concluir a requisição ao GitHub.")

    @staticmethod
    def _atraso(headers: dict, tentativa: int) -> int:
        retry_after = headers.get("Retry-After")
        if retry_after and str(retry_after).isdigit():
            return int(retry_after)
        return 2 ** tentativa

    @staticmethod
    def _normalizar(item: dict, agora) -> dict:
        licenca = item.get("license") or {}
        return {
            "chave_externa": str(item.get("id") or item.get("full_name", "")),
            "dados": {
                "id": item.get("id"),
                "full_name": item.get("full_name"),
                "html_url": item.get("html_url"),
                "description": item.get("description"),
                "language": item.get("language"),
                "licenca": licenca.get("spdx_id"),
                "estrelas": item.get("stargazers_count"),
                "forks": item.get("forks_count"),
                "issues_abertas": item.get("open_issues_count"),
                "criado_em": item.get("created_at"),
                "pushed_em": item.get("pushed_at"),
                "coletado_em": agora.isoformat(),
            },
        }
