import asyncio
from contextlib import asynccontextmanager
import logging
import subprocess

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.config import get_settings
from core.rate_limit import limiter
from data_platform.api.routers import router as data_platform_router
from data_platform.api.routers.internal import router as internal_router
from data_platform.api.routers.app_routes import router as app_routes_router

logger = logging.getLogger(__name__)


async def run_scheduler_loop() -> None:
    settings = get_settings()
    logger.info("Scheduler daemon background task initialized. Sleeping 10s before first run.")
    await asyncio.sleep(10)
    while True:
        logger.info("Background scheduler: triggering scheduled pipeline execution (make run-pipeline)...")
        try:
            process = await asyncio.create_subprocess_exec(
                "make", "run-pipeline",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                logger.info("Background scheduler: pipeline run completed successfully.")
            else:
                logger.error(
                    f"Background scheduler: pipeline run failed with code {process.returncode}. "
                    f"Stderr: {stderr.decode('utf-8', errors='replace')}"
                )
        except Exception as exc:
            logger.exception(f"Background scheduler encountered an unexpected error: {exc}")
        
        logger.info(f"Background scheduler: sleeping for {settings.scheduler_interval_seconds} seconds.")
        await asyncio.sleep(settings.scheduler_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    task = None
    if settings.scheduler_enabled:
        task = asyncio.create_task(run_scheduler_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(data_platform_router)
    app.include_router(internal_router)
    app.include_router(app_routes_router)

    @app.get("/health", tags=["system"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
