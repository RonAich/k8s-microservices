# 📋 Task Tracker Microservice

A production-grade FastAPI microservice for managing tasks, backed by Redis and deployed on Kubernetes. Built as a portfolio project demonstrating containerisation, orchestration, security hardening, and horizontal scalability.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Prerequisites](#prerequisites)
- [Running Locally (Docker Compose)](#running-locally-docker-compose)
- [Deploying to Minikube (Kubernetes)](#deploying-to-minikube-kubernetes)
- [Configuration](#configuration)
- [Production Design Decisions](#production-design-decisions)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Kubernetes Cluster                        │
│                                                                  │
│   ┌──────────────────────────────────────────────┐              │
│   │              task-tracker Deployment          │              │
│   │                                              │              │
│   │   ┌──────────┐  ┌──────────┐  ┌──────────┐  │              │
│   │   │  Pod 1   │  │  Pod 2   │  │  Pod 3   │  │  ← 3 replicas│
│   │   │ FastAPI  │  │ FastAPI  │  │ FastAPI  │  │    (baseline) │
│   │   │ :8000    │  │ :8000    │  │ :8000    │  │              │
│   │   └────┬─────┘  └────┬─────┘  └────┬─────┘  │              │
│   └────────┼─────────────┼─────────────┼─────────┘              │
│            └─────────────┼─────────────┘                        │
│                          │  ClusterIP                           │
│                   ┌──────▼──────┐                               │
│                   │redis-service│                               │
│                   │  :6379      │                               │
│                   └──────┬──────┘                               │
│                          │                                      │
│                   ┌──────▼──────┐                               │
│                   │Redis Pod    │                               │
│                   │redis:7.2    │                               │
│                   └─────────────┘                               │
│                                                                  │
│   ┌─────────────────┐      ┌─────────────────────────────────┐  │
│   │      HPA        │      │    task-tracker-service         │  │
│   │  min: 3         │      │    NodePort :30080              │  │
│   │  max: 10        │      └──────────────┬──────────────────┘  │
│   │  CPU target:70% │                     │                     │
│   └─────────────────┘                     │                     │
└───────────────────────────────────────────┼─────────────────────┘
                                            │
                                     ┌──────▼──────┐
                                     │  Your       │
                                     │  Browser /  │
                                     │  curl       │
                                     └─────────────┘
```

**Traffic flow:** An external request hits the `NodePort` service on port `30080`, which load-balances across all healthy `task-tracker` pods. Each pod talks to Redis through the internal `ClusterIP` service, resolved via Kubernetes DNS as `redis-service:6379`.

---

## Project Structure

```
task-tracker/
├── main.py               # FastAPI application (endpoints, Redis logic)
├── requirements.txt      # Pinned Python dependencies
├── Dockerfile            # Multi-stage build; runs as non-root appuser
├── .dockerignore         # Excludes dev artefacts from the build context
└── kubernetes.yaml       # All K8s manifests in a single file:
                          #   - Redis Deployment + ClusterIP Service
                          #   - App ConfigMap
                          #   - App Deployment (3 replicas, probes, securityContext)
                          #   - HorizontalPodAutoscaler
                          #   - App NodePort Service
```

---

## API Reference

| Method | Path | Description | Success Code |
|--------|------|-------------|--------------|
| `GET` | `/health` | Liveness + Redis reachability check | `200 OK` |
| `POST` | `/tasks` | Create a new task | `201 Created` |
| `GET` | `/tasks` | Retrieve all tasks (oldest first) | `200 OK` |

### `POST /tasks` — Request Body

```json
{
  "task": "Write the Kubernetes README"
}
```

### `POST /tasks` — Response Body

```json
{
  "id": "a3f1c2d4-...",
  "task": "Write the Kubernetes README",
  "created_at": "2024-11-01T10:30:00.000000+00:00"
}
```

### `GET /tasks` — Response Body

```json
[
  {
    "id": "a3f1c2d4-...",
    "task": "Write the Kubernetes README",
    "created_at": "2024-11-01T10:30:00.000000+00:00"
  }
]
```

### `GET /health` — Response Body

```json
{ "status": "ok", "redis": "ok" }
```

Returns `503 Service Unavailable` if Redis is unreachable.

---

## Prerequisites

### For local Docker Compose

| Tool | Minimum Version | Install |
|------|----------------|---------|
| Docker Desktop | 24.x | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose | v2.x | Bundled with Docker Desktop |

### For Kubernetes (Minikube)

| Tool | Minimum Version | Install |
|------|----------------|---------|
| Docker Desktop | 24.x | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Minikube | 1.32.x | [minikube.sigs.k8s.io](https://minikube.sigs.k8s.io/docs/start/) |
| kubectl | 1.29.x | [kubernetes.io/docs](https://kubernetes.io/docs/tasks/tools/) |

---

## Running Locally (Docker Compose)

The fastest way to run the full stack on your machine — no Kubernetes required.

**1. Create a `docker-compose.yml`** in the project root:

```yaml
services:
  redis:
    image: redis:7.2-alpine
    ports:
      - "6379:6379"

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      REDIS_HOST: redis
      REDIS_PORT: "6379"
    depends_on:
      - redis
```

**2. Build and start**

```bash
docker compose up --build
```

**3. Test the endpoints**

```bash
# Health check
curl http://localhost:8000/health

# Create a task
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "Deploy to Minikube"}'

# List all tasks
curl http://localhost:8000/tasks
```

**4. Interactive API docs**

Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser for the auto-generated Swagger UI.

**5. Tear down**

```bash
docker compose down
```

---

## Deploying to Minikube (Kubernetes)

### Step 1 — Start Minikube

```bash
minikube start

# Enable the metrics-server addon (required for the HPA to function)
minikube addons enable metrics-server
```

### Step 2 — Build the image inside Minikube's Docker daemon

This makes the image available to Minikube without pushing to a registry.

```bash
# Point your local Docker CLI at Minikube's internal daemon
eval $(minikube docker-env)

# Build the image (must match the image name in kubernetes.yaml)
docker build -t task-tracker:latest .
```

> **Windows (PowerShell):** Use `minikube docker-env | Invoke-Expression` instead.

### Step 3 — Apply all manifests

```bash
kubectl apply -f kubernetes.yaml
```

Expected output:

```
deployment.apps/redis created
service/redis-service created
configmap/task-tracker-config created
deployment.apps/task-tracker created
horizontalpodautoscaler.autoscaling/task-tracker-hpa created
service/task-tracker-service created
```

### Step 4 — Verify everything is running

```bash
# Watch pods come up (wait for all 4 to show Running)
kubectl get pods --watch

# Check the HPA registered a baseline
kubectl get hpa task-tracker-hpa

# Confirm services are created
kubectl get services
```

All `task-tracker` pods should show `2/2` under `READY` (readiness probe passing) before you proceed.

### Step 5 — Get the access URL

```bash
minikube service task-tracker-service --url
```

This prints a URL like `http://192.168.49.2:30080`. Use that in place of `localhost:8000` for all requests.

```bash
# Example
curl http://192.168.49.2:30080/health

curl -X POST http://192.168.49.2:30080/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "First Kubernetes task!"}'

curl http://192.168.49.2:30080/tasks
```

### Step 6 — Watch the HPA scale (optional load test)

```bash
# Terminal 1 — watch replica count in real time
kubectl get hpa task-tracker-hpa --watch

# Terminal 2 — generate load
# Install hey: https://github.com/rakyll/hey
hey -z 60s -c 50 http://$(minikube ip):30080/tasks
```

The HPA will scale from 3 → up to 10 replicas as CPU utilisation exceeds 70%, then scale back down after a 5-minute stabilisation window.

### Teardown

```bash
# Delete all resources defined in the manifest
kubectl delete -f kubernetes.yaml

# Stop Minikube (preserves cluster state)
minikube stop

# OR destroy the cluster entirely
minikube delete
```

---

## Configuration

All runtime configuration is injected via the `task-tracker-config` ConfigMap and consumed by the app through `os.getenv`.

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis hostname (set to `redis-service` in K8s) |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis logical database index |

> **Secrets:** If your Redis instance requires a password, do **not** put it in the ConfigMap. Create a `kubectl create secret generic redis-secret --from-literal=REDIS_PASSWORD=yourpassword` and reference it via `secretKeyRef` in the Deployment's `env` block.

---

## Production Design Decisions

### Multi-stage Docker build

The `Dockerfile` uses two stages. The **builder** stage installs all dependencies (including any C-extension compilers that pip may invoke) into an isolated prefix directory. The **runtime** stage starts from a clean `python:3.11-slim` base and copies only the compiled packages — no build tools, no pip, no compilers land in the shipped image. This minimises the attack surface and keeps the final image lean.

### Non-root container user

Both the Dockerfile (`adduser appuser`) and the Kubernetes `securityContext` (`runAsUser: 1001`, `runAsNonRoot: true`) ensure the process never runs as UID 0. If an attacker achieves remote code execution inside the container, they are confined to the permissions of an unprivileged user with no home directory and a read-only filesystem (`readOnlyRootFilesystem: true`).

### Liveness vs Readiness probes

The **liveness** probe (`periodSeconds: 20`) detects permanently broken pods — deadlocks, corrupted state — and triggers a container restart. The **readiness** probe (`periodSeconds: 10`) detects transient unavailability (e.g. Redis momentarily unreachable) and silently removes the pod from the Service's endpoint list without restarting it. Together they ensure users are only ever routed to healthy, ready pods.

### Resource requests and limits

**Requests** (`cpu: 50m`, `memory: 64Mi`) are the scheduler's guarantee — a node is only chosen if it can provide at least this much. **Limits** (`cpu: 100m`, `memory: 128Mi`) are kernel-enforced ceilings — CPU over-use is throttled, memory over-use triggers an OOMKill and restart. The gap between request and limit gives pods burst headroom without allowing one pod to starve its neighbours.

### HPA CPU threshold and stabilisation windows

The HPA targets 70% of the CPU *request* (35 millicores per pod). The `scaleUp.stabilizationWindowSeconds: 30` means it reacts to sustained spikes within 30 seconds. The `scaleDown.stabilizationWindowSeconds: 300` prevents flapping — the cluster waits a full 5 minutes of reduced load before removing replicas, avoiding a thrash cycle of scale-out → scale-in → scale-out under bursty traffic.

### Rolling update strategy

`maxUnavailable: 1` and `maxSurge: 1` mean a 3-replica deployment is always serving at least 2 pods during a rollout. New pods must pass the readiness probe before old pods are terminated, making every `kubectl set image` or `kubectl apply` a zero-downtime deployment.

---

## Troubleshooting

**Pods stuck in `Pending`**
```bash
kubectl describe pod <pod-name>
# Look for "Insufficient cpu" or "Insufficient memory" in Events —
# Minikube's default node may need more resources: minikube start --cpus=2 --memory=4g
```

**`ImagePullBackOff` on `task-tracker:latest`**
```bash
# You are likely outside Minikube's Docker context. Re-run:
eval $(minikube docker-env)
docker build -t task-tracker:latest .
```

**HPA shows `<unknown>` for CPU**
```bash
# metrics-server is not running
minikube addons enable metrics-server
kubectl rollout restart deployment task-tracker
```

**`/health` returns 503**
```bash
# Redis is unreachable — check redis pod status
kubectl get pods -l app=redis
kubectl logs deployment/redis
```

**Resetting task data**
```bash
# Flush Redis (all tasks are stored in a list under the key "tasks")
kubectl exec deployment/redis -- redis-cli FLUSHDB
```
