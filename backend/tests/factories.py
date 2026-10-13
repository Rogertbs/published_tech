import json


def gh_get(items):
    def _get(url, headers):
        return 200, {}, json.dumps({"items": items})

    return _get


def repo(id_, name, stars):
    return {
        "id": id_,
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "description": "d",
        "licenca": "MIT",
        "stargazers_count": stars,
    }


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Exemplo</title>
<item><title>Notícia A</title><link>https://exemplo.com/a</link>
<description>Resumo A</description><pubDate>Mon, 13 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>Notícia B</title><link>https://exemplo.com/b</link>
<description>Resumo B</description><pubDate>Sun, 12 Oct 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""


def get_feed(body=FEED):
    def _get(url, headers):
        return 200, {}, body

    return _get

