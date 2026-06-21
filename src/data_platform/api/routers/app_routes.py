import asyncio
import os
import sqlite3
import subprocess
from contextlib import suppress
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_async_session
from data_platform.api.auth import AuthUser, async_query as auth_query, get_current_user

router = APIRouter(tags=["app-ui-flows"])


class StatusUpdate(BaseModel):
    status: str


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)


async def _workspace_threat_count(workspace_id: str) -> int:
    try:
        rows = await auth_query(
            "SELECT COUNT(*) AS count FROM app_inference_event WHERE workspace_id = ?",
            (workspace_id,),
        )
        return int(rows[0]["count"]) if rows else 0
    except Exception:
        return 0


async def _workspace_has_cloudflare_integration(workspace_id: str) -> bool:
    try:
        rows = await auth_query(
            "SELECT 1 AS found FROM cloudflare_integration WHERE workspace_id = ? AND status IN ('pending_verification', 'active', 'provisioning') LIMIT 1",
            (workspace_id,),
        )
        return bool(rows)
    except Exception:
        return False


async def _session_payload(user: AuthUser) -> dict:
    threat_count = await _workspace_threat_count(user.workspace_id)
    has_integration = await _workspace_has_cloudflare_integration(user.workspace_id)
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "workspace_id": user.workspace_id,
        "workspace_name": user.workspace_name,
        "is_platform_admin": user.is_platform_admin,
        "has_cloudflare_integration": has_integration,
        "threat_count": threat_count,
        "onboarding_required": not user.is_platform_admin
        and not has_integration
        and threat_count == 0,
    }


def query_auth_db(query: str, params: tuple = ()) -> list[dict]:
    settings = get_settings()
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "").replace(
        "sqlite:///", ""
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.commit()
    conn.close()
    return [dict(r) for r in rows]


async def async_query_auth_db(query: str, params: tuple = ()) -> list[dict]:
    return await asyncio.to_thread(query_auth_db, query, params)


@router.get("/v1/auth/session")
async def get_session(current_user: AuthUser = Depends(get_current_user)) -> dict:
    return await _session_payload(current_user)


@router.patch("/v1/auth/profile")
async def patch_profile(
    payload: UpdateProfileRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    now = datetime.utcnow().isoformat() + "Z"
    await auth_query(
        'UPDATE "user" SET name = ?, updatedAt = ? WHERE id = ?',
        (payload.display_name.strip(), now, current_user.id),
    )
    await auth_query(
        "UPDATE app_workspace_membership SET display_name = ?, updated_at = ? WHERE auth_user_id = ?",
        (payload.display_name.strip(), now, current_user.id),
    )
    refreshed = AuthUser(
        id=current_user.id,
        email=current_user.email,
        display_name=payload.display_name.strip(),
        role=current_user.role,
        workspace_id=current_user.workspace_id,
        workspace_name=current_user.workspace_name,
        is_platform_admin=current_user.is_platform_admin,
    )
    return await _session_payload(refreshed)


@router.get("/v1/stats/kpi")
async def get_kpis(
    session: AsyncSession = Depends(get_async_session),
    current_user: AuthUser = Depends(get_current_user),
):
    try:
        raw_count = await _workspace_threat_count(current_user.workspace_id)
        norm_count = raw_count
        dataset_item_count = 0
        if current_user.is_platform_admin:
            with suppress(Exception):
                dataset_item_count = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM data_dataset_item")
                    )
                ).scalar() or 0
    except Exception:
        raw_count, norm_count, dataset_item_count = 0, 0, 0

    phishing_count = 0
    spam_count = 0
    legitimate_count = 0

    try:
        rows = await async_query_auth_db(
            "SELECT safety_verdict, COUNT(*) as cnt FROM app_inference_event WHERE workspace_id = ? GROUP BY safety_verdict",
            (current_user.workspace_id,),
        )
        for row in rows:
            verdict = row["safety_verdict"]
            count = row["cnt"]
            if verdict == "phishing":
                phishing_count = count
            elif verdict == "spam":
                spam_count = count
            elif verdict == "legitimate":
                legitimate_count = count
    except Exception:
        pass

    return {
        "raw_records_count": raw_count,
        "normalized_messages_count": norm_count,
        "dataset_items_count": dataset_item_count,
        "threats_phishing_count": phishing_count,
        "threats_spam_count": spam_count,
        "threats_legitimate_count": legitimate_count,
    }


@router.get("/v1/threats")
async def get_threats(current_user: AuthUser = Depends(get_current_user)):
    try:
        rows = await async_query_auth_db(
            """
            SELECT
                id,
                id AS message_id,
                subject,
                sender,
                snippet AS body_preview,
                safety_verdict AS verdict,
                composite_score AS confidence,
                created_at AS received_at,
                COALESCE(override_verdict, 'active') AS status
            FROM app_inference_event
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            """,
            (current_user.workspace_id,),
        )
        threats = []
        for row in rows:
            status = row["status"]
            if status not in ("active", "trashed", "restored"):
                status = "active"
            threats.append(
                {
                    "id": row["id"],
                    "message_id": row["message_id"],
                    "subject": row["subject"],
                    "sender": row["sender"],
                    "body_preview": row["body_preview"],
                    "verdict": row["verdict"],
                    "confidence": row["confidence"],
                    "received_at": row["received_at"],
                    "status": status,
                }
            )
        return threats
    except Exception:
        return []


@router.post("/v1/threats/{id}/status")
async def update_threat_status(
    id: str,
    payload: StatusUpdate,
    current_user: AuthUser = Depends(get_current_user),
):
    if payload.status not in ("active", "trashed", "restored"):
        raise HTTPException(status_code=400, detail="Invalid status value")
    try:
        await async_query_auth_db(
            "UPDATE app_inference_event SET override_verdict = ?, overridden_at = ? WHERE id = ? AND workspace_id = ?",
            (
                payload.status,
                datetime.utcnow().isoformat() + "Z",
                id,
                current_user.workspace_id,
            ),
        )
        rows = await async_query_auth_db(
            "SELECT id, id AS message_id, subject, sender, snippet AS body_preview, safety_verdict AS verdict, composite_score AS confidence, created_at AS received_at, override_verdict AS status FROM app_inference_event WHERE id = ? AND workspace_id = ?",
            (id, current_user.workspace_id),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Threat not found")
        row = rows[0]
        return {
            "id": row["id"],
            "message_id": row["message_id"],
            "subject": row["subject"],
            "sender": row["sender"],
            "body_preview": row["body_preview"],
            "verdict": row["verdict"],
            "confidence": row["confidence"],
            "received_at": row["received_at"],
            "status": (
                row["status"]
                if row["status"] in ("active", "trashed", "restored")
                else "active"
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


@router.get("/v1/datasets")
async def list_datasets_alias(session: AsyncSession = Depends(get_async_session)):
    try:
        result = await session.execute(
            text(
                "SELECT id, version_tag, item_count, status, published_at FROM data_dataset ORDER BY version_tag DESC"
            )
        )
        rows = result.all()
        return [
            {
                "id": str(row.id),
                "version_tag": row.version_tag,
                "item_count": row.item_count,
                "status": row.status,
                "published_at": (
                    f"{row.published_at.isoformat()}Z" if row.published_at else None
                ),
            }
            for row in rows
        ]
    except Exception:
        return []


def execute_pipeline():
    try:
        subprocess.run(["make", "run-pipeline"], check=True)
    except Exception as exc:
        print(f"Pipeline execution failed: {exc}")


@router.post("/v1/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(execute_pipeline)
    return {"run_id": "incremental-pipeline-run-triggered"}


@router.get("/auth/login/google")
async def google_login_redirect():
    settings = get_settings()
    if settings.google_client_id and settings.google_redirect_uri:
        from urllib.parse import urlencode

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": "sicurre-oauth-state",
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return RedirectResponse(url=auth_url)

    return RedirectResponse(
        url="/auth/callback/google?code=mock-oauth-code-48293&state=mock-state-xyz"
    )


@router.get("/auth/callback/google")
async def google_oauth_callback(
    request: Request, code: str = "mock-code", state: str = "mock-state"
):
    settings = get_settings()

    referer = request.headers.get("referer", "")
    frontend_base = "http://localhost:5173"
    if "3000" in referer:
        frontend_base = "http://localhost:3000"
    elif "8001" in referer:
        frontend_base = "http://localhost:8001"
    elif "8000" in referer:
        frontend_base = "http://localhost:8000"

    if (
        settings.google_client_id
        and settings.google_client_secret
        and code != "mock-oauth-code-48293"
    ):
        import httpx

        async with httpx.AsyncClient() as client:
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            }
            token_res = await client.post(token_url, data=token_data)
            if token_res.status_code != 200:
                return RedirectResponse(
                    url=f"{frontend_base}/login?error=Google%20Token%20Exchange%20Failed"
                )

            tokens = token_res.json()
            access_token = tokens.get("access_token")
            userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
            userinfo_res = await client.get(
                userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
            )
            if userinfo_res.status_code != 200:
                return RedirectResponse(
                    url=f"{frontend_base}/login?error=Google%20User%20Info%20Failed"
                )

            user_info = userinfo_res.json()
            name = user_info.get("name", "Utilisateur Google")
            email = user_info.get("email") or "google-user@sicurre.local"
            redirect_url = (
                f"{frontend_base}/?auth_provider=google"
                f"&username={name}"
                f"&email={email}"
            )
            return RedirectResponse(url=redirect_url)

    return RedirectResponse(
        url=f"{frontend_base}/login?error=Google%20OAuth%20not%20configured"
    )
