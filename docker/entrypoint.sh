#!/bin/sh
# Seed persistent volumes on first start, then hand over to the CMD (gunicorn).
set -eu

if [ ! -f /app/data/site.json ]; then
  echo "entrypoint: data volume is empty — seeding initial content"
  cp -a /app/seed/data/. /app/data/
fi
[ -f /app/data/users.json ] || echo "[]" > /app/data/users.json
[ -f /app/data/messages.json ] || echo "[]" > /app/data/messages.json

if [ -z "$(ls -A /app/static/uploads 2>/dev/null)" ]; then
  echo "entrypoint: uploads volume is empty — seeding images"
  cp -a /app/seed/uploads/. /app/static/uploads/
fi

if [ -z "${SECRET_KEY:-}" ]; then
  echo "entrypoint: WARNING — SECRET_KEY is not set; a key will be generated and stored in the data volume."
fi

if [ "$(cat /app/data/users.json)" = "[]" ]; then
  echo "entrypoint: no admin user yet — run: docker compose exec app python manage.py create-admin"
fi

exec "$@"
