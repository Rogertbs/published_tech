import json
import re
import time
from datetime import datetime

from django.utils import timezone

from sources.connectors.base import Conector, requisitar_com_retry, urllib_get
from sources.models import CategoriaModelo

API_URL = "https://huggingface.co/api/models"
DESCONHECIDO = "Desconhecido"
FORMATOS = ("gguf", "safetensors", "awq", "gptq", "onnx", "openvino", "mlx", "pytorch")
_VARIANTE_RE = re.compile(
    r"[-_. ](gguf|awq|gptq|int4|int8|4bit|8bit|fp16|bf16|fp8|lora|dpo|sft|merge|merged|"
    r"uncensored|quantized|q\d(_[a-z0-9]+)*)$",
    re.IGNORECASE,
)


def _tag(tags: list, prefixo: str):
    for tag in tags or []:
        if tag.startswith(prefixo):
            return tag[len(prefixo):]
    return None


def _formatos(tags: list) -> list:
    inferiores = {tag.lower() for tag in tags or []}
    return [formato for formato in FORMATOS if formato in inferiores]


def _parametros(item: dict):
    total = (item.get("safetensors") or {}).get("total")
    if isinstance(total, int) and total > 0:
        return total
    return DESCONHECIDO


def _idade_dias(iso) -> int | None:
    if not iso:
        return None
    try:
        momento = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (timezone.now() - momento).days


def _familia(dados: dict) -> str:
    base = dados.get("base_model")
    if base and base != DESCONHECIDO:
        return base.lower()
    identificador = str(dados.get("id") or "").lower()
    anterior = None
    while anterior != identificador:
        anterior = identificador
        identificador = _VARIANTE_RE.sub("", identificador)
    return identificador


def classificar(dados: dict) -> str:
    if dados.get("lancamento_confirmado"):
        return CategoriaModelo.LANCAMENTO_CONFIRMADO
    base = dados.get("base_model")
    if base and base != DESCONHECIDO:
        return CategoriaModelo.NOVA_VARIANTE
    dias = _idade_dias(dados.get("metadados", {}).get("criado_em"))
    if dias is not None and dias > 180 and float(dados.get("trendingScore") or 0) > 0:
        return CategoriaModelo.MODELO_ANTIGO_ATENCAO
    return CategoriaModelo.ATUALIZACAO_REPOSITORIO


class HuggingFaceConector(Conector):
    tipo = "huggingface"

    def listar(self, parametros: dict, token: str | None, *, http_get=urllib_get, sleep=time.sleep):
        parametros = parametros or {}
        limite = max(1, min(int(parametros.get("limite", 30)), 100))
        ordenacao = parametros.get("sort", "trendingScore")
        consulta = [f"sort={ordenacao}", "direction=-1", f"limit={limite}", "full=true"]
        if parametros.get("pipeline_tag"):
            consulta.append(f"filter={parametros['pipeline_tag']}")
        if parametros.get("search"):
            consulta.append(f"search={parametros['search']}")
        if parametros.get("author"):
            consulta.append(f"author={parametros['author']}")
        url = f"{API_URL}?{'&'.join(consulta)}"

        headers = {"Accept": "application/json", "User-Agent": "published-tech"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        _, _, corpo = requisitar_com_retry(url, headers, http_get, sleep, nome="Hugging Face")
        payload = json.loads(corpo or "[]")
        if isinstance(payload, dict):
            payload = payload.get("models", [])
        agora = timezone.now()
        normalizados = [self._normalizar(item, agora) for item in payload]
        return self._agrupar_familias(normalizados)

    @staticmethod
    def _normalizar(item: dict, agora) -> dict:
        tags = item.get("tags") or []
        identificador = item.get("id") or item.get("modelId") or ""
        autor = item.get("author") or (
            identificador.split("/")[0] if "/" in identificador else DESCONHECIDO
        )
        base_model = _tag(tags, "base_model:")
        if base_model and base_model.endswith(":adapter"):
            base_model = base_model[: -len(":adapter")]
        lancamento_confirmado = bool(item.get("lancamento_confirmado"))
        dados = {
            "id": identificador,
            "organizacao": autor,
            "url": f"https://huggingface.co/{identificador}",
            "tarefa": item.get("pipeline_tag") or DESCONHECIDO,
            "biblioteca": item.get("library_name") or DESCONHECIDO,
            "parametros": _parametros(item),
            "formatos": _formatos(tags),
            "base_model": base_model or DESCONHECIDO,
            "licenca": _tag(tags, "license:") or DESCONHECIDO,
            "acesso_restrito": bool(item.get("gated")) or bool(item.get("private")),
            "trendingScore": item.get("trendingScore"),
            "metadados": {
                "downloads": item.get("downloads"),
                "likes": item.get("likes"),
                "criado_em": item.get("createdAt"),
                "modificado_em": item.get("lastModified"),
                "coletado_em": agora.isoformat(),
            },
            "lancamento_confirmado": lancamento_confirmado,
            "data_lancamento": (item.get("data_lancamento") or DESCONHECIDO)
            if lancamento_confirmado
            else DESCONHECIDO,
            "anuncio": DESCONHECIDO,
            "evidencias": [f"https://huggingface.co/{identificador}"],
            "origem": "metadado_coletado",
            "verificado": False,
        }
        dados["familia"] = _familia(dados)
        dados["categoria"] = classificar(dados)
        return {"chave_externa": dados["familia"], "dados": dados}

    @staticmethod
    def _agrupar_familias(normalizados: list[dict]) -> list[dict]:
        familias: dict[str, dict] = {}
        for registro in normalizados:
            chave = registro["dados"]["familia"]
            atual = familias.get(chave)
            if atual is None:
                registro["dados"]["variantes"] = [registro["dados"]["id"]]
                familias[chave] = registro
                continue
            atual["dados"]["variantes"].append(registro["dados"]["id"])
            if float(registro["dados"].get("trendingScore") or 0) > float(
                atual["dados"].get("trendingScore") or 0
            ):
                registro["dados"]["variantes"] = atual["dados"]["variantes"]
                familias[chave] = registro
        return list(familias.values())
