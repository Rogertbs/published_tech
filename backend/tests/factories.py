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
