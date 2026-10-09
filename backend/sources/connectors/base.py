import urllib.error
import urllib.request


class ConectorError(Exception):
    pass


class ConectorIndisponivel(ConectorError):
    pass


class RateLimitPersistente(ConectorError):
    pass


def urllib_get(url: str, headers: dict, timeout: int = 10):
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConectorIndisponivel(str(exc)) from exc


def header(headers: dict, nome: str):
    alvo = nome.lower()
    for chave, valor in headers.items():
        if chave.lower() == alvo:
            return valor
    return None


def atraso(headers: dict, tentativa: int) -> int:
    retry_after = header(headers, "Retry-After")
    if retry_after and str(retry_after).isdigit():
        return int(retry_after)
    return 2 ** tentativa


def requisitar_com_retry(url, headers, http_get, sleep, *, nome, max_tentativas=3):
    for tentativa in range(1, max_tentativas + 1):
        status, headers_resposta, corpo = http_get(url, headers)
        restantes = header(headers_resposta, "X-RateLimit-Remaining")
        if status == 429 or (status == 403 and restantes == "0"):
            if tentativa >= max_tentativas:
                raise RateLimitPersistente(f"Limite de taxa do {nome} atingido.")
            sleep(atraso(headers_resposta, tentativa))
            continue
        if status >= 500:
            if tentativa >= max_tentativas:
                raise ConectorIndisponivel(f"{nome} respondeu HTTP {status}.")
            sleep(2 ** tentativa)
            continue
        if status >= 400:
            raise ConectorError(f"{nome} respondeu HTTP {status}.")
        return status, headers_resposta, corpo
    raise ConectorIndisponivel(f"Não foi possível concluir a requisição ao {nome}.")


class Conector:
    tipo = ""

    def listar(self, parametros: dict, token: str | None, *, http_get, sleep) -> list[dict]:
        raise NotImplementedError
