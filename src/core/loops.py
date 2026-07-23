import logging
from typing import Any

import httpx

from core.config import get_settings

logger = logging.getLogger("sicurre.loops")
LOOPS_TRANSACTIONAL_URL = "https://app.loops.so/api/v1/transactional"

async def send_loops_transactional(
    email: str,
    transactional_id: str | None,
    data_variables: dict[str, Any],
) -> bool:
    """Send a transactional email using the Loops.so API.

    Args:
        email: The recipient's email address.
        transactional_id: The transaction template ID from Loops.
        data_variables: Dict containing template variables.

    Returns:
        bool: True if the request was successful, False otherwise.
    """
    settings = get_settings()
    api_key = settings.loops_api_key

    if not api_key:
        logger.warning("Loops API key not configured. Skipping email dispatch to %s.", email)
        return False

    if not transactional_id:
        logger.warning("Loops Transactional ID is missing. Skipping email dispatch to %s.", email)
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "transactionalId": transactional_id,
        "email": email,
        "dataVariables": data_variables,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                LOOPS_TRANSACTIONAL_URL,
                json=payload,
                headers=headers,
            )
            
            # Handle successful response
            if response.status_code in (200, 201):
                logger.info("Successfully sent Loops transactional email %s to %s.", transactional_id, email)
                return True
            else:
                logger.error(
                    "Failed to send Loops email %s to %s. Status code: %d, Response: %s",
                    transactional_id,
                    email,
                    response.status_code,
                    response.text,
                )
                return False
    except Exception as exc:
        logger.exception("Exception occurred while sending Loops email to %s: %s", email, exc)
        return False
