import time

import feedparser
from django.utils import timezone

from sources.connectors.base import Conector, ConectorError, requisitar_com_retry, urllib_get


class RSSConector(Conector):
    tipo = "rss"

    def listar(self, parametros: dict, token: str | None, *, http_get=urllib_get, sleep=time.sleep):
        parametros = parametros or {}
        url = parametros.get("feed_url")
        if not url:
            raise ConectorError("Parâmetro 'feed_url' ausente para a fonte RSS.")
        limite = max(1, min(int(parametros.get("limite", 20)), 50))
        headers = {
            "User-Agent": "published-tech",
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        }
        _, _, corpo = requisitar_com_retry(url, headers, http_get, sleep, nome="RSS")
        feed = feedparser.parse(corpo)
        agora = timezone.now()
        nome_fonte = parametros.get("nome_fonte", "")

        registros = []
        for entry in feed.entries[:limite]:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue
            registros.append(
                {
                    "chave_externa": link,
                    "dados": {
                        "id": link,
                        "full_name": entry.get("title", ""),
                        "titulo": entry.get("title", ""),
                        "url": link,
                        "resumo": entry.get("summary") or entry.get("description") or "",
                        "publicado_em": entry.get("published") or entry.get("updated") or "",
                        "fonte": nome_fonte,
                        "coletado_em": agora.isoformat(),
                    },
                }
            )
        return registros
