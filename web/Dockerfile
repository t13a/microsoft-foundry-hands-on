# The web app: BFF (FastAPI) serving the built SPA. Build from the repository root:
#   docker build -f web/Dockerfile .

FROM node:22-slim AS ui
WORKDIR /src
COPY web/ui/package.json web/ui/package-lock.json ./
RUN npm ci
COPY web/ui/ ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1
WORKDIR /app
# The workspace lock needs every member's pyproject, but only web-api and catalog are installed.
COPY pyproject.toml uv.lock ./
COPY agent/pyproject.toml agent/pyproject.toml
COPY packages/catalog packages/catalog
COPY web/api web/api
RUN uv sync --package web-api --frozen --no-dev --no-editable
COPY --from=ui /src/dist /app/static
ENV PATH=/app/.venv/bin:$PATH STATIC_DIR=/app/static HOST=0.0.0.0 PORT=8000
EXPOSE 8000
USER nobody
CMD ["python", "-m", "web_api"]
