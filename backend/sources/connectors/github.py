import json
import time
from datetime import timedelta

from django.utils import timezone

from sources.connectors.base import Conector, ConectorError, requisitar_com_retry, urllib_get

API_URL = "https://api.github.com/search/repositories"
API_VERSION = "2026-03-10"
LIMITE_QUERY = 256


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
        consulta = "+".join(qualificadores)
        if len(consulta) > LIMITE_QUERY:
            raise ConectorError("Consulta do GitHub excede o limite de 256 caracteres.")
        url = f"{API_URL}?q={consulta}&sort=stars&order=desc&per_page={limite}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "published-tech",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        _, _, corpo = requisitar_com_retry(
            url, headers, http_get, sleep, nome="GitHub"
        )
        payload = json.loads(corpo or "{}")
        agora = timezone.now()
        return [self._normalizar(item, agora) for item in payload.get("items", [])]

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
                "licenca": licenca.get("spdx_id") or "Desconhecida",
                "estrelas": item.get("stargazers_count"),
                "forks": item.get("forks_count"),
                "issues_abertas": item.get("open_issues_count"),
                "criado_em": item.get("created_at"),
                "pushed_em": item.get("pushed_at"),
                "coletado_em": agora.isoformat(),
            },
        }
