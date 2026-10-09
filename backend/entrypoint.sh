#!/usr/bin/env bash
set -euo pipefail

if [ "${START_REDIS:-true}" = "true" ]; then
  redis-server --daemonize yes --save "" --appendonly no --bind 0.0.0.0 --protected-mode no
fi

echo "Aguardando o banco de dados..."
for _ in $(seq 1 60); do
  if python manage.py migrate --noinput >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
python manage.py migrate --noinput

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ]; then
  python manage.py createsuperuser --noinput 2>/dev/null || true
fi

if [ "${START_JOBS:-true}" = "true" ]; then
  python manage.py run_worker --loop &
  python manage.py run_scheduler --loop &
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
