class IlustracaoIndisponivel(Exception):
    pass


def gerar_ilustracao(descricao: str = "") -> dict:
    return {
        "url": "/static/ilustracoes/placeholder.png",
        "legenda": "Ilustração gerada por IA (simulada)",
        "mocada": True,
        "descricao": descricao,
    }
