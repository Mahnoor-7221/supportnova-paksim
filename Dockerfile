# ---------- Stage 1: build the React frontend ----------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: FastAPI backend (also serves the built frontend) ----------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=frontend /app/frontend/dist frontend/dist

WORKDIR /app/backend
ENV APP_ENV=production DEBUG=false SEED_ON_STARTUP=true
EXPOSE 8000
# Render/Railway inject $PORT; falls back to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
