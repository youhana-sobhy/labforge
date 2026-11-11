FROM python:3.12-slim

LABEL org.opencontainers.image.title="LabForge" \
      org.opencontainers.image.description="On-demand virtual network labs"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LABFORGE_HOME=/data
WORKDIR /app
COPY pyproject.toml README.md ./
COPY labforge ./labforge
RUN pip install --no-cache-dir . && mkdir -p /data

EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')"
CMD ["labforge", "serve", "--host", "0.0.0.0", "--port", "8080"]
