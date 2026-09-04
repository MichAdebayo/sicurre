from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base, get_async_session
from data_platform.api.main import create_app

AUTH_HEADERS = {"Authorization": "Bearer dev-token"}


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_and_list_source_systems(client: AsyncClient) -> None:
    create_response = await client.post(
        "/v1/data/sources",
        headers=AUTH_HEADERS,
        json={
            "name": "cert-fr-cti",
            "source_type": "scraping",
            "description": "CERT-FR threat intel reports",
            "owner_name": "ANSSI",
            "legal_basis": "legitimate_interest",
            "contains_personal_data": False,
            "retention_days": 365,
        },
    )

    assert create_response.status_code == 201
    created_item = create_response.json()
    assert created_item["name"] == "cert-fr-cti"
    assert created_item["source_type"] == "scraping"
    assert created_item["is_active"] is True

    list_response = await client.get("/v1/data/sources", headers=AUTH_HEADERS)

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == created_item["id"]


@pytest.mark.asyncio
async def test_create_and_list_ingestion_runs(client: AsyncClient) -> None:
    source_response = await client.post(
        "/v1/data/sources",
        headers=AUTH_HEADERS,
        json={
            "name": "bigquery-phishing-fr",
            "source_type": "bigdata",
        },
    )
    source_id = source_response.json()["id"]

    create_response = await client.post(
        "/v1/data/ingestion-runs",
        headers=AUTH_HEADERS,
        json={
            "source_system_id": source_id,
            "started_at": "2026-03-17T09:00:00Z",
            "status": "running",
            "trigger_mode": "manual",
            "raw_object_count": 3,
            "raw_record_count": 120,
            "log_message": "Initial import",
        },
    )

    assert create_response.status_code == 201
    created_item = create_response.json()
    assert created_item["source_system_id"] == source_id
    assert created_item["status"] == "running"
    assert created_item["raw_record_count"] == 120

    list_response = await client.get(
        "/v1/data/ingestion-runs",
        headers=AUTH_HEADERS,
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == created_item["id"]


@pytest.mark.asyncio
async def test_create_ingestion_run_requires_existing_source_system(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/v1/data/ingestion-runs",
        headers=AUTH_HEADERS,
        json={
            "source_system_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "started_at": "2026-03-17T09:00:00Z",
            "status": "pending",
            "trigger_mode": "manual",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_data_routes_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/v1/data/sources")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_source_list_rate_limit_returns_429(client: AsyncClient) -> None:
    rate_limit_headers = {"Authorization": "Bearer dev-rate-limit"}

    for _ in range(60):
        response = await client.get("/v1/data/sources", headers=rate_limit_headers)
        assert response.status_code == 200

    blocked_response = await client.get(
        "/v1/data/sources",
        headers=rate_limit_headers,
    )
    assert blocked_response.status_code == 429
