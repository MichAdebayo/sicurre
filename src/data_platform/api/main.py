import asyncio
from contextlib import asynccontextmanager
import logging
import subprocess

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from core.config import get_settings
from core.rate_limit import limiter
from data_platform.api.routers import router as data_platform_router
from data_platform.api.routers.internal import router as internal_router
from data_platform.api.routers.app_routes import router as app_routes_router
from data_platform.api.routers.integrations import router as integrations_router

logger = logging.getLogger(__name__)


def configure_tracing(app: FastAPI) -> None:
    """Export a small sample of useful API traces through the local Alloy collector."""
    settings = get_settings()
    if not settings.telemetry_traces_enabled:
        return
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "sicurre-api",
                "deployment.environment.name": settings.environment,
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(settings.telemetry_trace_sample_ratio)),
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.telemetry_otlp_endpoint))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,metrics,docs,openapi.json,redoc",
    )


async def run_scheduler_loop() -> None:
    settings = get_settings()
    logger.info(
        "Scheduler daemon initialized for source ingestion only. Sleeping 10s before first run."
    )
    await asyncio.sleep(10)
    while True:
        logger.info(
            "Background scheduler: triggering scheduled ingestion execution (make run-scheduler)..."
        )
        try:
            process = await asyncio.create_subprocess_exec(
                "make", "run-scheduler", stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                logger.info(
                    "Background scheduler: source ingestion run completed successfully."
                )
            else:
                logger.error(
                    f"Background scheduler: source ingestion run failed with code {process.returncode}. "
                    f"Stderr: {stderr.decode('utf-8', errors='replace')}"
                )
        except Exception as exc:
            logger.exception(
                f"Background scheduler encountered an unexpected error: {exc}"
            )

        logger.info(
            f"Background scheduler: sleeping for {settings.scheduler_interval_seconds} seconds."
        )
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
    app.include_router(integrations_router)
    configure_tracing(app)

    @app.get("/health", tags=["system"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
