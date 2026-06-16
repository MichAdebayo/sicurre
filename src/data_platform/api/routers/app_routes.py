import os
import asyncio
import sqlite3
import subprocess
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import get_settings
from core.database import get_async_session

router = APIRouter(tags=["app-ui-flows"])

class StatusUpdate(BaseModel):
    status: str

# Helper to run synchronous SQLite queries against sicurre.db
def query_auth_db(query: str, params: tuple = ()) -> list[dict]:
    settings = get_settings()
    # parse the database path from settings.database_url (sqlite+aiosqlite:///...)
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    
    # Ensure directory path exists
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


# ── 1. KPI Stats Endpoint ──
@router.get("/v1/stats/kpi")
async def get_kpis(session: AsyncSession = Depends(get_async_session)):
    try:
        raw_count = (await session.execute(text("SELECT COUNT(*) FROM data_raw_record"))).scalar() or 0
        norm_count = (await session.execute(text("SELECT COUNT(*) FROM data_normalized_message"))).scalar() or 0
        dataset_item_count = 0
        try:
            dataset_item_count = (await session.execute(text("SELECT COUNT(*) FROM data_dataset_item"))).scalar() or 0
        except Exception:
            pass
    except Exception as e:
        # Fallback if dataplatform DB schema is empty/not updated yet
        raw_count, norm_count, dataset_item_count = 0, 0, 0

    phishing_count = 0
    spam_count = 0
    legitimate_count = 0
    
    try:
        rows = await async_query_auth_db(
            "SELECT safety_verdict, COUNT(*) as cnt FROM poc_inference_event GROUP BY safety_verdict"
        )
        for r in rows:
            verdict = r["safety_verdict"]
            cnt = r["cnt"]
            if verdict == "phishing":
                phishing_count = cnt
            elif verdict == "spam":
                spam_count = cnt
            elif verdict == "legitimate":
                legitimate_count = cnt
    except Exception:
        # If sicurre.db is not yet seeded, ensure we return 0 rather than crashing
        pass

    return {
        "raw_records_count": raw_count,
        "normalized_messages_count": norm_count,
        "dataset_items_count": dataset_item_count,
        "threats_phishing_count": phishing_count,
        "threats_spam_count": spam_count,
        "threats_legitimate_count": legitimate_count,
    }


# ── 2. Threat Logs Endpoint ──
@router.get("/v1/threats")
async def get_threats():
    try:
        rows = await async_query_auth_db(
            """
            SELECT 
                id,
                id as message_id,
                subject,
                snippet as body_preview,
                safety_verdict as verdict,
                composite_score as confidence,
                created_at as received_at,
                COALESCE(override_verdict, 'active') as status
            FROM poc_inference_event
            ORDER BY created_at DESC
            """
        )
        threats = []
        for r in rows:
            status = r["status"]
            if status not in ("active", "trashed", "restored"):
                status = "active"
            threats.append({
                "id": r["id"],
                "message_id": r["message_id"],
                "subject": r["subject"],
                "body_preview": r["body_preview"],
                "verdict": r["verdict"],
                "confidence": r["confidence"],
                "received_at": r["received_at"],
                "status": status
            })
        return threats
    except Exception as e:
        # Return empty list rather than crashing if DB is empty
        return []


# ── 3. Update Threat Status ──
@router.post("/v1/threats/{id}/status")
async def update_threat_status(id: str, payload: StatusUpdate):
    if payload.status not in ("active", "trashed", "restored"):
        raise HTTPException(status_code=400, detail="Invalid status value")
    try:
        await async_query_auth_db(
            "UPDATE poc_inference_event SET override_verdict = ?, overridden_at = ? WHERE id = ?",
            (payload.status, datetime.utcnow().isoformat() + "Z", id)
        )
        rows = await async_query_auth_db(
            "SELECT id, id as message_id, subject, snippet as body_preview, safety_verdict as verdict, composite_score as confidence, created_at as received_at, override_verdict as status FROM poc_inference_event WHERE id = ?",
            (id,)
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Threat not found")
        r = rows[0]
        return {
            "id": r["id"],
            "message_id": r["message_id"],
            "subject": r["subject"],
            "body_preview": r["body_preview"],
            "verdict": r["verdict"],
            "confidence": r["confidence"],
            "received_at": r["received_at"],
            "status": r["status"] if r["status"] in ("active", "trashed", "restored") else "active"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


# ── 4. Datasets List Alias ──
@router.get("/v1/datasets")
async def list_datasets_alias(session: AsyncSession = Depends(get_async_session)):
    try:
        result = await session.execute(text("SELECT id, version_tag, item_count, status, published_at FROM data_dataset ORDER BY version_tag DESC"))
        rows = result.all()
        datasets = []
        for r in rows:
            datasets.append({
                "id": str(r.id),
                "version_tag": r.version_tag,
                "item_count": r.item_count,
                "status": r.status,
                "published_at": r.published_at.isoformat() + "Z" if r.published_at else None
            })
        return datasets
    except Exception:
        return []


# ── 5. Run Incremental Pipeline ──
def execute_pipeline():
    try:
        subprocess.run(["make", "run-pipeline"], check=True)
    except Exception as e:
        print(f"Pipeline execution failed: {e}")

@router.post("/v1/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(execute_pipeline)
    return {"run_id": "incremental-pipeline-run-triggered"}


# ── 6. Mock Google OAuth Login Flow ──
@router.get("/auth/login/google")
async def google_login_redirect():
    # Redirect immediately to the callback route with mock tokens/state
    return RedirectResponse(
        url="/auth/callback/google?code=mock-oauth-code-48293&state=mock-state-xyz"
    )

@router.get("/auth/callback/google")
async def google_oauth_callback(code: str = "mock-code", state: str = "mock-state"):
    # Redirect user back to the React app port (3000) with credentials
    redirect_url = (
        "http://localhost:3000/?session_token=mock-google-oauth-token-2026"
        "&username=Michael%20Adebayo"
    )
    return RedirectResponse(url=redirect_url)
