from fastapi import APIRouter, Depends

from core.security import require_authenticated_principal

from data_platform.api.routers.ingestion_runs import (
    router as ingestion_runs_router,
)
from data_platform.api.routers.source_systems import (
    router as source_systems_router,
)
from data_platform.api.routers.annotations import (
    router as annotations_router,
)
from data_platform.api.routers.datasets import router as datasets_router
from data_platform.api.routers.messages import router as messages_router
from data_platform.api.routers.raw_records import (
    router as raw_records_router,
)


router = APIRouter(
    prefix="/v1/data",
    dependencies=[Depends(require_authenticated_principal)],
)
router.include_router(source_systems_router)
router.include_router(ingestion_runs_router)
router.include_router(raw_records_router)
router.include_router(messages_router)
router.include_router(annotations_router)
router.include_router(datasets_router)

__all__ = ["router"]
