# ── Stage 1: build frontend ──────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

# ── Stage 2: final image ─────────────────────────────────────────────────────
# Plain Python alpine is used intentionally: the HA base images run s6-overlay
# which does not forward container environment variables (including
# SUPERVISOR_TOKEN) to child processes, breaking HA sensor pushes.
FROM python:3.11-alpine
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
