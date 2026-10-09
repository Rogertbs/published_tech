import time

from django.core.management.base import BaseCommand

from jobs import services


class Command(BaseCommand):
    help = "Cria tarefas recorrentes a partir dos agendamentos (uma vez, ou em loop com --loop)."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Executa continuamente.")
        parser.add_argument("--interval", type=float, default=5.0, help="Segundos entre execuções.")

    def handle(self, *args, **options):
        while True:
            criadas = services.rodar_agendador()
            if not options["loop"]:
                self.stdout.write(f"Tarefas criadas: {criadas}")
                break
            time.sleep(options["interval"])
