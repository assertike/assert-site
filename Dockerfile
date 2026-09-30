# ASSERT website + CMS — production image
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Unprivileged runtime user
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --chown=app:app . .

# Keep a pristine copy of the shipped content; the entrypoint uses it to seed
# empty volumes (first start, or bind mounts) without overwriting live edits.
RUN mkdir -p /app/seed \
 && cp -a /app/data /app/seed/data \
 && cp -a /app/static/uploads /app/seed/uploads \
 && rm -f /app/seed/data/.secret_key /app/seed/data/users.json /app/seed/data/messages.json \
 && rm -rf /app/seed/data/.backups \
 && chmod +x /app/docker/entrypoint.sh \
 && chown -R app:app /app/seed /app/data /app/static/uploads

USER app

VOLUME ["/app/data", "/app/static/uploads"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'), timeout=4)" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "docker/gunicorn.conf.py", "app:create_app()"]
