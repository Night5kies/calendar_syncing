import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.api.v1.share import load_active_share_link
from app.db.session import SessionLocal
from app.models.meeting_request import MeetingRequest
from app.models.share_link import ShareLink
from app.services.share_links import (
    compute_expires_at,
    delete_expired_share_links,
    is_share_link_expired,
)


class ShareLinkExpiryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def test_compute_expires_at_adds_ttl_days(self) -> None:
        self.assertEqual(
            compute_expires_at(self.now, ttl_days=30),
            self.now + timedelta(days=30),
        )

    def test_link_with_future_expiry_is_not_expired(self) -> None:
        link = SimpleNamespace(expires_at=self.now + timedelta(days=1))
        self.assertFalse(is_share_link_expired(link, now=self.now))

    def test_link_with_past_expiry_is_expired(self) -> None:
        link = SimpleNamespace(expires_at=self.now - timedelta(seconds=1))
        self.assertTrue(is_share_link_expired(link, now=self.now))

    def test_null_expiry_is_never_expired(self) -> None:
        # Legacy rows created before TTL existed must keep working.
        link = SimpleNamespace(expires_at=None)
        self.assertFalse(is_share_link_expired(link, now=self.now))


class LoadActiveShareLinkTests(unittest.TestCase):
    """DB-backed: route helper enforces existence + expiry."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        try:
            self.db.connection()
        except OperationalError as exc:
            self.db.close()
            self.skipTest(f"Postgres not reachable for db-backed test: {exc}")
        self.event = MeetingRequest(
            organizer_id=uuid.uuid4(),
            title="Share TTL test",
            duration_min=60,
            timezone="America/New_York",
            status="sent",
        )
        self.db.add(self.event)
        self.db.flush()

    def tearDown(self) -> None:
        self.db.rollback()
        self.db.close()

    def _link(self, token: str, expires_at) -> ShareLink:
        link = ShareLink(meeting_request_id=self.event.id, token=token, expires_at=expires_at)
        self.db.add(link)
        self.db.flush()
        return link

    def test_missing_token_raises_404(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            load_active_share_link(self.db, "does-not-exist")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_active_link_is_returned(self) -> None:
        now = datetime.now(timezone.utc)
        self._link("active-token", now + timedelta(days=1))
        link = load_active_share_link(self.db, "active-token")
        self.assertEqual(link.token, "active-token")

    def test_expired_link_raises_410(self) -> None:
        now = datetime.now(timezone.utc)
        self._link("expired-token", now - timedelta(seconds=1))
        with self.assertRaises(HTTPException) as ctx:
            load_active_share_link(self.db, "expired-token")
        self.assertEqual(ctx.exception.status_code, 410)

    def test_null_expiry_link_is_returned(self) -> None:
        self._link("legacy-token", None)
        link = load_active_share_link(self.db, "legacy-token")
        self.assertEqual(link.token, "legacy-token")


class DeleteExpiredShareLinksTests(unittest.TestCase):
    """DB-backed: cleanup job removes only expired rows."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        try:
            self.db.connection()
        except OperationalError as exc:
            self.db.close()
            self.skipTest(f"Postgres not reachable for db-backed test: {exc}")
        self.event = MeetingRequest(
            organizer_id=uuid.uuid4(),
            title="Cleanup test",
            duration_min=60,
            timezone="America/New_York",
            status="sent",
        )
        self.db.add(self.event)
        self.db.flush()

    def tearDown(self) -> None:
        self.db.rollback()
        self.db.close()

    def _link(self, token: str, expires_at) -> None:
        self.db.add(ShareLink(meeting_request_id=self.event.id, token=token, expires_at=expires_at))
        self.db.flush()

    def test_deletes_only_expired_links(self) -> None:
        now = datetime.now(timezone.utc)
        self._link("expired-1", now - timedelta(days=2))
        self._link("expired-2", now - timedelta(seconds=1))
        self._link("active", now + timedelta(days=5))
        self._link("legacy-null", None)

        deleted = delete_expired_share_links(self.db, now=now)

        self.assertEqual(deleted, 2)
        remaining = {
            link.token
            for link in self.db.query(ShareLink)
            .filter(ShareLink.meeting_request_id == self.event.id)
            .all()
        }
        self.assertEqual(remaining, {"active", "legacy-null"})


if __name__ == "__main__":
    unittest.main()
