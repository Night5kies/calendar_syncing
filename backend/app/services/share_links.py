"""Share-link lifecycle helpers: expiry computation and enforcement."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.share_link import ShareLink


class _HasExpiry(Protocol):
    expires_at: datetime | None


def compute_expires_at(now: datetime, ttl_days: int) -> datetime:
    """Expiry timestamp for a freshly created share link."""
    return now + timedelta(days=ttl_days)


def is_share_link_expired(link: _HasExpiry, now: datetime | None = None) -> bool:
    """True when a link has a populated expiry in the past.

    Links with a null ``expires_at`` (legacy rows created before TTL existed)
    never expire, so existing shared URLs keep working.
    """
    if link.expires_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return link.expires_at <= now


def delete_expired_share_links(db: Session, now: datetime | None = None) -> int:
    """Delete share links whose expiry is in the past. Returns the count removed.

    Rows with a null ``expires_at`` are left alone (see ``is_share_link_expired``).
    """
    now = now or datetime.now(timezone.utc)
    result = db.execute(
        delete(ShareLink).where(
            ShareLink.expires_at.is_not(None),
            ShareLink.expires_at <= now,
        )
    )
    return result.rowcount or 0
