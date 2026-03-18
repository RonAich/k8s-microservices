import os
import uuid
import json
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))
TASKS_KEY  = "tasks"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Task Tracker",
    description="Lightweight task microservice backed by Redis.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Redis lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event() -> None:
    app.state.redis = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await app.state.redis.aclose()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class TaskIn(BaseModel):
    task: str = Field(..., min_length=1, max_length=1024, description="Task description")


class TaskOut(BaseModel):
    id: str
    task: str
    created_at: str


class HealthResponse(BaseModel):
    status: str
    redis: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def get_redis() -> aioredis.Redis:
    return app.state.redis


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness / readiness probe",
    tags=["ops"],
)
async def health() -> HealthResponse:
    """
    Returns HTTP 200 when the service is healthy and Redis is reachable.
    Returns HTTP 503 when Redis is unavailable — safe for K8s readiness probes.
    """
    r = await get_redis()
    try:
        await r.ping()
        redis_status = "ok"
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unreachable: {exc}",
        )
    return HealthResponse(status="ok", redis=redis_status)


@app.post(
    "/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
    tags=["tasks"],
)
async def create_task(payload: TaskIn) -> TaskOut:
    """
    Persists a task string to Redis as a JSON-serialised list entry.
    Each task receives a UUID and an ISO-8601 UTC timestamp.
    """
    r = await get_redis()
    task_obj = TaskOut(
        id=str(uuid.uuid4()),
        task=payload.task,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    try:
        await r.rpush(TASKS_KEY, task_obj.model_dump_json())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not write to Redis: {exc}",
        )
    return task_obj


@app.get(
    "/tasks",
    response_model=list[TaskOut],
    summary="Retrieve all tasks",
    tags=["tasks"],
)
async def list_tasks() -> list[TaskOut]:
    """
    Returns every task stored in Redis, oldest first.
    Returns an empty list when no tasks exist.
    """
    r = await get_redis()
    try:
        raw_items: list[str] = await r.lrange(TASKS_KEY, 0, -1)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not read from Redis: {exc}",
        )
    return [TaskOut(**json.loads(item)) for item in raw_items]
