from typing import Callable

HANDLERS: dict[str, Callable] = {}


def register(tipo_tarefa: str):
    def decorator(func: Callable):
        HANDLERS[tipo_tarefa] = func
        return func

    return decorator


def get_handler(tipo_tarefa: str) -> Callable | None:
    return HANDLERS.get(tipo_tarefa)


@register("eco")
def eco(tarefa):
    return {"mensagem": tarefa.parametros.get("mensagem", "ok"), "tarefa": tarefa.pk}
