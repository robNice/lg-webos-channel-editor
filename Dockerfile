# LG WebOS Channel Editor – container image (GHCR, see .github/workflows).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LG_EDITOR_HOST=0.0.0.0 \
    LG_EDITOR_PORT=8765

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY LICENSE README.md README.de.md TECHNICAL.md TECHNICAL.de.md ./
COPY *.py ./
COPY static/ static/
COPY locales/ locales/

# Working copy, backups, settings and confirmed TV host keys (data/known_hosts).
# Mount a host directory here so they survive image updates.
RUN mkdir -p /app/data
VOLUME /app/data

EXPOSE 8765

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/' % os.environ.get('LG_EDITOR_PORT', '8765'), timeout=4)" || exit 1

CMD ["python", "app.py"]
