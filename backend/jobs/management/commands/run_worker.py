import os
import time

from django.core.management.base import BaseCommand

from jobs import services


class Command(BaseCommand):
    help = "Processa tarefas da fila (uma vez, ou em loop com --loop)."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Executa continuamente.")
        parser.add_argument("--interval", type=float, default=2.0, help="Segundos entre buscas.")
        parser.add_argument("--worker-id", default=None)

    def handle(self, *args, **options):
        worker_id = options["worker_id"] or f"worker-{os.getpid()}"
        while True:
            services.recuperar_abandonadas()
            processou = services.processar_uma(worker_id)
            if not options["loop"]:
                break
            if not processou:
                time.sleep(options["interval"])
