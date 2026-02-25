"""
Audit Event Service for NSE Trader (G3).

Provides durable persistence for:
- NO_TRADE decisions (with full provenance)
- Signal lifecycle events
- System audit trail

Every write is non-blocking (fire-and-forget with error logging).
All records carry provenance metadata.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session_factory
from app.db.models import NoTradeEvent, AuditEvent, Signal

logger = logging.getLogger(__name__)


class AuditService:
    """
    Durable audit trail writer.

    All methods are async and swallow exceptions to avoid
    disrupting the main request path. Failures are logged.
    """

    async def _get_session(self) -> AsyncSession:
        factory = get_session_factory()
        return factory()

    # ------------------------------------------------------------------
    # NO_TRADE events
    # ------------------------------------------------------------------

    async def record_no_trade(
        self,
        symbol: Optional[str],
        reason_code: str,
        detail: Optional[str] = None,
        confidence: Optional[float] = None,
        scope: str = "symbol",
        provenance: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a NO_TRADE decision."""
        try:
            session = await self._get_session()
            async with session:
                event = NoTradeEvent(
                    ts=datetime.now(timezone.utc),
                    scope=scope,
                    symbol=symbol.upper() if symbol else None,
                    reason_code=reason_code,
                    detail=detail,
                    confidence=confidence,
                    provenance=provenance or {},
                )
                session.add(event)
                await session.commit()
                logger.info(
                    "NO_TRADE persisted: scope=%s symbol=%s reason=%s",
                    scope, symbol, reason_code,
                )
        except Exception as e:
            logger.error("Failed to persist NO_TRADE event: %s", e)

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------

    async def record_audit(
        self,
        component: str,
        event_type: str,
        message: str,
        level: str = "INFO",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a generic audit event."""
        try:
            session = await self._get_session()
            async with session:
                event = AuditEvent(
                    ts=datetime.now(timezone.utc),
                    component=component,
                    level=level,
                    event_type=event_type,
                    message=message,
                    payload=payload or {},
                )
                session.add(event)
                await session.commit()
        except Exception as e:
            logger.error("Failed to persist audit event: %s", e)

    # ------------------------------------------------------------------
    # Signal persistence
    # ------------------------------------------------------------------

    async def record_signal(
        self,
        signal_id: str,
        symbol: str,
        as_of: datetime,
        strategy: str,
        horizon: str,
        direction: str,
        confidence: float,
        status: str = "ACTIVE",
        bias_probability: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
        provenance: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        """Persist a generated signal."""
        try:
            session = await self._get_session()
            async with session:
                signal = Signal(
                    signal_id=signal_id,
                    symbol=symbol.upper(),
                    as_of=as_of,
                    strategy=strategy,
                    horizon=horizon,
                    direction=direction,
                    confidence=confidence,
                    bias_probability=bias_probability,
                    status=status,
                    params=params or {},
                    provenance=provenance or {},
                    created_at=datetime.now(timezone.utc),
                    expires_at=expires_at,
                )
                session.add(signal)
                await session.commit()
                logger.info(
                    "Signal persisted: %s %s %s conf=%.2f status=%s",
                    signal_id, symbol, direction, confidence, status,
                )
        except Exception as e:
            logger.error("Failed to persist signal: %s", e)

    # ------------------------------------------------------------------
    # Query helpers (for health/debug endpoints)
    # ------------------------------------------------------------------

    async def get_recent_no_trade_events(
        self, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent NO_TRADE events for debugging."""
        try:
            from sqlalchemy import select
            session = await self._get_session()
            async with session:
                stmt = (
                    select(NoTradeEvent)
                    .order_by(NoTradeEvent.ts.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                events = result.scalars().all()
                return [
                    {
                        "ts": e.ts.isoformat(),
                        "scope": e.scope,
                        "symbol": e.symbol,
                        "reason_code": e.reason_code,
                        "detail": e.detail,
                        "confidence": e.confidence,
                        "provenance": e.provenance,
                    }
                    for e in events
                ]
        except Exception as e:
            logger.error("Failed to query NO_TRADE events: %s", e)
            return []

    async def get_recent_audit_events(
        self, component: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent audit events."""
        try:
            from sqlalchemy import select
            session = await self._get_session()
            async with session:
                stmt = select(AuditEvent).order_by(AuditEvent.ts.desc()).limit(limit)
                if component:
                    stmt = stmt.where(AuditEvent.component == component)
                result = await session.execute(stmt)
                events = result.scalars().all()
                return [
                    {
                        "ts": e.ts.isoformat(),
                        "component": e.component,
                        "level": e.level,
                        "event_type": e.event_type,
                        "message": e.message,
                        "payload": e.payload,
                    }
                    for e in events
                ]
        except Exception as e:
            logger.error("Failed to query audit events: %s", e)
            return []


# Singleton
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get singleton audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
