FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock.txt pyproject.toml ./
COPY itmo_aimedicine/ ./itmo_aimedicine/
RUN pip install --no-cache-dir -r requirements.lock.txt && pip install --no-cache-dir --no-deps .
COPY data/therapy/ ./data/therapy/
COPY data/therapy-expansion/ ./data/therapy-expansion/
COPY research/therapy-expansion/ ./research/therapy-expansion/
COPY reports/therapy-expansion/ ./reports/therapy-expansion/
COPY reports/therapy-expansion-gemma-compatible/ ./reports/therapy-expansion-gemma-compatible/
COPY research/therapy/ ./research/therapy/
COPY reports/therapy/ ./reports/therapy/
COPY reports/therapy-revision/ ./reports/therapy-revision/
COPY --from=frontend /build/frontend/dist ./frontend/dist/
RUN useradd --uid 10001 --create-home appuser && mkdir -p reports/live data/private/sources && chown -R appuser:appuser /app
USER appuser
ENV PUBLIC_DEMO=1 DEMO_ALLOW_LIVE=0 LLM_MODE=mock
EXPOSE 8001
CMD ["uvicorn", "itmo_aimedicine.api:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
