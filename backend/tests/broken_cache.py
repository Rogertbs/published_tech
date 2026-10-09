from django.core.cache.backends.base import BaseCache


class BrokenCache(BaseCache):
    def __init__(self, location, params):
        super().__init__(params)

    def get(self, *args, **kwargs):
        raise RuntimeError("cache indisponível")

    def set(self, *args, **kwargs):
        raise RuntimeError("cache indisponível")

    def add(self, *args, **kwargs):
        raise RuntimeError("cache indisponível")

    def delete(self, *args, **kwargs):
        raise RuntimeError("cache indisponível")
