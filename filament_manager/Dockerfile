ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.11-alpine3.19

# ── Stage 1: build frontend ──────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

# ── Stage 2: final image ─────────────────────────────────────────────────────
FROM ${BUILD_FROM}
WORKDIR /app

LABEL org.opencontainers.image.title="Filament Manager" \
      org.opencontainers.image.description="Track 3D printer filament inventory, print history and costs" \
      org.opencontainers.image.source="https://github.com/cgradl/filament-manager" \
      org.opencontainers.image.licenses="MIT"

# Build deps for some Python packages
RUN apk add --no-cache gcc musl-dev libffi-dev

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/
COPY --from=frontend-builder /frontend/dist/ ./static/
COPY config.yaml /config.yaml
COPY CHANGELOG.md /CHANGELOG.md
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
