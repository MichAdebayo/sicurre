from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.config import get_settings
from core.rate_limit import limiter
from data_platform.api.routers import router as data_platform_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(data_platform_router)

    @app.get("/health", tags=["system"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
