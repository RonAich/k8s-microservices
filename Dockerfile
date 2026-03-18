# =============================================================================
# Stage 1 — Dependency builder
# =============================================================================
# Use the full image so we have pip + build tools available.
FROM python:3.11-slim AS builder

# Keeps Python from generating .pyc files and enables stdout/stderr flushing.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install dependencies into an isolated prefix so Stage 2 can COPY them in
# as a single layer — no build tools land in the final image.
COPY requirements.txt .
RUN pip install --upgrade pip --quiet && \
    pip install --quiet --prefix=/install --no-cache-dir -r requirements.txt


# =============================================================================
# Stage 2 — Lean runtime image
# =============================================================================
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Tell Python where to find the packages we copied from Stage 1.
    PYTHONPATH=/app/site-packages

# ── Security: non-root user ───────────────────────────────────────────────────
RUN addgroup --system appgroup && \
    adduser  --system --ingroup appgroup --no-create-home appuser

# ── Copy installed packages from builder ─────────────────────────────────────
COPY --from=builder /install/lib/python3.11/site-packages /app/site-packages

# ── Copy installed console scripts (uvicorn binary) ──────────────────────────
COPY --from=builder /install/bin /usr/local/bin

# ── Copy application source ───────────────────────────────────────────────────
WORKDIR /app
COPY main.py .

# Hand ownership of the app directory to the non-root user.
RUN chown -R appuser:appgroup /app

USER appuser

# Expose the port uvicorn will bind to.
EXPOSE 8000

# ── Health-check for Docker / Compose ────────────────────────────────────────
# K8s uses its own liveness/readiness probes; this is a convenience for local dev.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# ── Runtime command ───────────────────────────────────────────────────────────
# Use exec-form so signals (SIGTERM) reach uvicorn directly, not a shell.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
