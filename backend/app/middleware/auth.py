"""
API Key authentication for beta deployment.

Usage:
  - Protected routes use `Depends(require_api_key)`.
  - Key is passed via the X-API-Key header (configurable).
  - Keys stored as SHA-256 hashes in the `api_keys` table.
  - In development (ENV=dev), auth is bypassed with a warning log.

CLI to create a key:
  python -m app.cli.auth create-key --name "my-laptop"
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.engine import get_async_session
from app.db.models import ApiKey

logger = logging.getLogger(__name__)

_settings = get_settings()
_api_key_header = APIKeyHeader(name=_settings.API_KEY_HEADER, auto_error=False)


def hash_key(plain: str) -> str:
    """SHA-256 hash of a plain-text API key."""
    return hashlib.sha256(plain.encode()).hexdigest()


def generate_key() -> str:
    """Generate a cryptographically secure API key (48 URL-safe chars)."""
    return secrets.token_urlsafe(36)


async def require_api_key(
    api_key: Optional[str] = Security(_api_key_header),
    session: AsyncSession = Depends(get_async_session),
) -> Optional[ApiKey]:
    """
    FastAPI dependency that enforces API key auth.

    In dev mode (ENV=dev), auth is bypassed.
    In any other mode, a valid active key is required.
    """
    env = os.environ.get("ENV", "dev").lower()

    if env == "dev":
        # Dev bypass — allow unauthenticated access with a warning
        if not api_key:
            logger.debug("Auth bypassed in dev mode (no key provided)")
            return None
        # If a key IS provided in dev, still validate it (for testing)

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide via X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key_hash_val = hash_key(api_key)
    stmt = select(ApiKey).where(
        ApiKey.key_hash == key_hash_val,
        ApiKey.is_active == True,
    )
    result = await session.execute(stmt)
    db_key = result.scalar_one_or_none()

    if db_key is None:
        raise HTTPException(
            status_code=403,
            detail="Invalid or deactivated API key.",
        )

    # Touch last_used_at (fire-and-forget, don't fail request on error)
    try:
        await session.execute(
            update(ApiKey)
            .where(ApiKey.id == db_key.id)
            .values(last_used_at=datetime.now(timezone.utc))
        )
        await session.commit()
    except Exception:
        await session.rollback()

    return db_key
