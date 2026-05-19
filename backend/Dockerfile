# MarketPulse India — backend image (local dev / ECS)
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Kolkata

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl build-essential \
 && rm -rf /var/lib/apt/lists/* \
 && ln -fs /usr/share/zoneinfo/Asia/Kolkata /etc/localtime

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY backend ./backend
COPY agents ./agents
COPY mcp_servers ./mcp_servers

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
