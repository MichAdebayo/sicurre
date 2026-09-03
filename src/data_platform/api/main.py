import asyncio
import logging
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import SQLAlchemyError

from core.config import get_settings
from core.db_keepalive import keepalive_enabled, run_db_keepalive
from core.inference_client import close_inference_client
from core.provider_credentials import encrypt_legacy_provider_credentials
from core.rate_limit import limiter
from data_platform.api.routers import router as data_platform_router
from data_platform.api.routers.app_routes import router as app_routes_router
from data_platform.api.routers.app_routes import synchronize_operational_exercises
from data_platform.api.routers.integrations import router as integrations_router
from data_platform.api.routers.internal import router as internal_router
from data_platform.api.routers.reported_email import router as reported_email_router
from data_platform.api.schemas.integration_responses import HealthResponse

logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {"name": "system", "description": "Process health and deployment metadata."},
    {"name": "data-sources", "description": "Registered dataset source systems."},
    {"name": "data-ingestion", "description": "Source ingestion run lineage."},
    {"name": "data-raw-records", "description": "Authorized raw-record retrieval."},
    {"name": "data-messages", "description": "Normalized message curation."},
    {"name": "data-annotations", "description": "Human and automated annotations."},
    {"name": "data-datasets", "description": "Versioned dataset assembly and publication."},
    {"name": "internal", "description": "Bearer-protected service-to-service contracts."},
    {"name": "app-ui-flows", "description": "Authenticated workspace and administration flows."},
    {"name": "integrations", "description": "Cloudflare routing and email scan gateways."},
    {"name": "reported-email", "description": "False-negative and DMARC report ingestion."},
]


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
                logger.info("Background scheduler: source ingestion run completed successfully.")
            else:
                logger.error(
                    f"Background scheduler: source ingestion run failed with code {process.returncode}. "
                    f"Stderr: {stderr.decode('utf-8', errors='replace')}"
                )
        except Exception as exc:
            logger.exception(f"Background scheduler encountered an unexpected error: {exc}")

        logger.info(
            f"Background scheduler: sleeping for {settings.scheduler_interval_seconds} seconds."
        )
        await asyncio.sleep(settings.scheduler_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.operational_tests_enabled:
        try:
            await synchronize_operational_exercises()
        except SQLAlchemyError:
            logger.warning("Exercise state restoration deferred until the next admin refresh")
    if settings.environment.lower() in {"production", "prod"}:
        migrated_credentials = await encrypt_legacy_provider_credentials(settings)
        if migrated_credentials:
            logger.info("Encrypted %d legacy provider credential record(s)", migrated_credentials)
    task = None
    if settings.scheduler_enabled:
        task = asyncio.create_task(run_scheduler_loop())
    # Keeps one pooled connection open so a scan does not pay connection setup
    # to a suspended serverless database inside its latency budget.
    keepalive = asyncio.create_task(run_db_keepalive()) if keepalive_enabled() else None
    try:
        yield
    finally:
        await close_inference_client()
        for background in (task, keepalive):
            if background:
                background.cancel()
                try:
                    await background
                except asyncio.CancelledError:
                    pass


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Sicurre Platform API",
        summary="Data, application, and integration contracts for Sicurre.",
        description=(
            "Generated from the deployed FastAPI routes and Pydantic models. "
            "Authenticated customer operations use Better Auth sessions or bearer tokens; "
            "internal and email-gateway routes require their documented service credentials."
        ),
        version="1.0.0",
        openapi_tags=OPENAPI_TAGS,
        servers=[{"url": "/", "description": "Current Sicurre deployment"}],
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def _no_store_on_api(request, call_next):
        """Forbid caching of API responses.

        An absent Cache-Control is not "do not cache" — it licenses heuristic
        freshness, so a cache may store the response and pick its own lifetime.
        /v1/threats and /v1/quarantine return sender addresses and subject
        lines, which is third-party personal data; stored to disk it outlives
        the session that was allowed to see it, and a back-navigation after
        logout can render it without the server ever being consulted.

        Applied as middleware rather than per route so an endpoint added later
        cannot be shipped without it. The root document already sets no-store;
        this closes the same gap on the API.
        """
        response = await call_next(request)
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Cookie, Authorization"
        return response

    app.include_router(data_platform_router)
    app.include_router(internal_router)
    app.include_router(app_routes_router)
    app.include_router(integrations_router)
    app.include_router(reported_email_router)
    configure_tracing(app)

    @app.get("/health", tags=["system"], response_model=HealthResponse)
    @limiter.exempt
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    @app.get("/metrics", include_in_schema=False)
    @limiter.exempt
    async def metrics() -> Response:
        """Expose bounded application metrics to the private Alloy scraper."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
