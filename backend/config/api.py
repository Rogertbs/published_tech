from django.conf import settings
from django.http import JsonResponse


def autorizado(request) -> bool:
    token = getattr(settings, "INTERNAL_API_TOKEN", None)
    if not token:
        return True
    return request.headers.get("X-Internal-Token") == token


def json_response(payload, status=200) -> JsonResponse:
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
