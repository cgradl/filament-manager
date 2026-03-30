# ── Stage 1: build frontend ──────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

# ── Stage 2: final image ─────────────────────────────────────────────────────
FROM python:3.11-alpine
WORKDIR /app

# Build deps for some Python packages
RUN apk add --no-cache gcc musl-dev libffi-dev

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/
COPY --from=frontend-builder /frontend/dist/ ./static/
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
