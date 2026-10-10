FROM ghcr.io/astral-sh/uv:0.12.5 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY survey_machine ./survey_machine
RUN uv sync --frozen --no-dev --no-editable --extra local --extra postgres \
    && useradd --system --uid 10001 --create-home survey \
    && mkdir -p /app/data \
    && chown survey:survey /app/data
USER survey
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
CMD ["/app/.venv/bin/uvicorn", "survey_machine.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
