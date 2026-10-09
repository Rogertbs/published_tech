class ConectorError(Exception):
    pass


class ConectorIndisponivel(ConectorError):
    pass


class RateLimitPersistente(ConectorError):
    pass


class Conector:
    tipo = ""

    def listar(self, parametros: dict, token: str | None, *, http_get, sleep) -> list[dict]:
        raise NotImplementedError
