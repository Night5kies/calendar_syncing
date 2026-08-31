"""DB-backed coverage for cache pruning, busy rebuilds, and disconnect purge."""
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.v1 import calendar as api
from app.db.session import SessionLocal
from app.models.availability_block import AvailabilityBlock
from app.models.busy_cache import BusyCache
from app.models.calendar_connection import CalendarConnection
from app.models.calendar_sync_state import CalendarSyncState
from app.models.event_cache import EventCache
from app.models.profile import Profile
from app.models.provider_calendar import ProviderCalendar

WINDOW_START = datetime(2026, 3, 2, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 3, 9, tzinfo=timezone.utc)


def _event(event_id: str, start: datetime, end: datetime, calendar_id: str = "primary") -> dict:
    return {
        "provider": "google",
        "provider_event_id": event_id,
        "provider_calendar_id": calendar_id,
        "start_at": start,
        "end_at": end,
        "is_all_day": False,
        "timezone": "UTC",
        "title": f"Event {event_id}",
        "location": None,
        "is_private": False,
        "etag": f"etag-{event_id}",
    }


class CalendarCacheTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        try:
            self.db.connection()
        except OperationalError as exc:
            self.db.close()
            self.skipTest(f"Postgres not reachable for db-backed test: {exc}")

        self.user_id = uuid.uuid4()
        self.db.add(Profile(id=self.user_id, email=f"user-{self.user_id}@example.com"))
        self.db.flush()

    def tearDown(self) -> None:
        if getattr(self, "db", None) is None:
            return
        self.db.rollback()
        self.db.close()

    def _add_calendar(self, calendar_id: str, *, enabled: bool = True, primary: bool = False):
        self.db.add(
            ProviderCalendar(
                user_id=self.user_id,
                provider="google",
                provider_calendar_id=calendar_id,
                name=calendar_id,
                is_primary=primary,
                is_enabled=enabled,
                updated_at=datetime.now(timezone.utc),
            )
        )
        self.db.flush()

    def _add_connection(self) -> CalendarConnection:
        connection = CalendarConnection(
            user_id=self.user_id,
            provider="google",
            provider_account_id="acct",
            access_token="tok",
            refresh_token="ref",
        )
        self.db.add(connection)
        self.db.flush()
        return connection

    def _cached_event_ids(self) -> set[str]:
        return set(
            self.db.execute(
                select(EventCache.provider_event_id).where(EventCache.user_id == self.user_id)
            )
            .scalars()
            .all()
        )

    def _busy(self) -> list[tuple[datetime, datetime]]:
        return [
            (row[0], row[1])
            for row in self.db.execute(
                select(BusyCache.start_at, BusyCache.end_at)
                .where(BusyCache.user_id == self.user_id)
                .order_by(BusyCache.start_at)
            ).all()
        ]


class SyncEventCacheTests(CalendarCacheTestCase):
    def test_deleted_events_are_pruned(self) -> None:
        first = _event(
            "a",
            datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
            datetime(2026, 3, 3, 11, tzinfo=timezone.utc),
        )
        second = _event(
            "b",
            datetime(2026, 3, 4, 10, tzinfo=timezone.utc),
            datetime(2026, 3, 4, 11, tzinfo=timezone.utc),
        )
        api.sync_event_cache(
            self.db, self.user_id, "google", ["primary"], WINDOW_START, WINDOW_END, [first, second]
        )
        self.assertEqual(self._cached_event_ids(), {"a", "b"})

        # "b" was deleted upstream; the next sync must not leave it blocking time.
        api.sync_event_cache(
            self.db, self.user_id, "google", ["primary"], WINDOW_START, WINDOW_END, [first]
        )
        self.assertEqual(self._cached_event_ids(), {"a"})

    def test_moved_events_do_not_leave_a_ghost(self) -> None:
        original = _event(
            "a",
            datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
            datetime(2026, 3, 3, 11, tzinfo=timezone.utc),
        )
        api.sync_event_cache(
            self.db, self.user_id, "google", ["primary"], WINDOW_START, WINDOW_END, [original]
        )

        moved = _event(
            "a",
            datetime(2026, 3, 3, 15, tzinfo=timezone.utc),
            datetime(2026, 3, 3, 16, tzinfo=timezone.utc),
        )
        api.sync_event_cache(
            self.db, self.user_id, "google", ["primary"], WINDOW_START, WINDOW_END, [moved]
        )

        rows = self.db.execute(
            select(EventCache.start_at).where(EventCache.user_id == self.user_id)
        ).scalars().all()
        # The old 10:00 row used to survive as a second entry and stay "busy".
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].astimezone(timezone.utc).hour, 15)

    def test_empty_result_clears_the_window(self) -> None:
        api.sync_event_cache(
            self.db,
            self.user_id,
            "google",
            ["primary"],
            WINDOW_START,
            WINDOW_END,
            [
                _event(
                    "a",
                    datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
                    datetime(2026, 3, 3, 11, tzinfo=timezone.utc),
                )
            ],
        )
        api.sync_event_cache(
            self.db, self.user_id, "google", ["primary"], WINDOW_START, WINDOW_END, []
        )
        self.assertEqual(self._cached_event_ids(), set())

    def test_events_outside_the_window_are_untouched(self) -> None:
        outside = _event(
            "outside",
            datetime(2026, 4, 1, 10, tzinfo=timezone.utc),
            datetime(2026, 4, 1, 11, tzinfo=timezone.utc),
        )
        api.sync_event_cache(
            self.db,
            self.user_id,
            "google",
            ["primary"],
            datetime(2026, 4, 1, tzinfo=timezone.utc),
            datetime(2026, 4, 2, tzinfo=timezone.utc),
            [outside],
        )
        api.sync_event_cache(
            self.db, self.user_id, "google", ["primary"], WINDOW_START, WINDOW_END, []
        )
        self.assertEqual(self._cached_event_ids(), {"outside"})


class EnsureEventCacheTests(CalendarCacheTestCase):
    def test_busy_includes_availability_blocks_without_any_connection(self) -> None:
        # The old per-connection loop skipped the busy rebuild entirely when the
        # user had no calendar connected, losing their manual blocks.
        self.db.add(
            AvailabilityBlock(
                user_id=self.user_id,
                start_at=datetime(2026, 3, 3, 9, tzinfo=timezone.utc),
                end_at=datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
                type="busy",
            )
        )
        self.db.flush()

        api.ensure_event_cache(self.db, self.user_id, WINDOW_START, WINDOW_END, [])
        self.assertEqual(
            self._busy(),
            [
                (
                    datetime(2026, 3, 3, 9, tzinfo=timezone.utc),
                    datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
                )
            ],
        )

    def test_synced_window_is_not_refetched(self) -> None:
        self._add_calendar("primary", primary=True)
        connection = self._add_connection()

        with mock.patch.object(api.google, "fetch_events", return_value=[]) as fetch:
            api.ensure_event_cache(
                self.db, self.user_id, WINDOW_START, WINDOW_END, [connection]
            )
            self.assertEqual(fetch.call_count, 1)
            # An empty window is now cacheable, so the second call hits nothing.
            api.ensure_event_cache(
                self.db, self.user_id, WINDOW_START, WINDOW_END, [connection]
            )
            self.assertEqual(fetch.call_count, 1)

    def test_provider_failure_falls_back_to_cached_data(self) -> None:
        self._add_calendar("primary", primary=True)
        connection = self._add_connection()
        api.sync_event_cache(
            self.db,
            self.user_id,
            "google",
            ["primary"],
            WINDOW_START,
            WINDOW_END,
            [
                _event(
                    "a",
                    datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
                    datetime(2026, 3, 3, 11, tzinfo=timezone.utc),
                )
            ],
        )

        with mock.patch.object(
            api.google, "fetch_events", side_effect=RuntimeError("google down")
        ):
            # Must not raise: a provider outage cannot take the endpoint down.
            api.ensure_event_cache(
                self.db, self.user_id, WINDOW_START, WINDOW_END, [connection]
            )

        self.assertEqual(self._cached_event_ids(), {"a"})
        self.assertEqual(len(self._busy()), 1)

    def test_busy_is_rebuilt_once_across_providers(self) -> None:
        """A second provider must not erase the first provider's busy blocks."""
        self._add_calendar("primary", primary=True)
        self.db.add(
            ProviderCalendar(
                user_id=self.user_id,
                provider="other",
                provider_calendar_id="other-cal",
                name="Other",
                is_enabled=True,
                updated_at=datetime.now(timezone.utc),
            )
        )
        self.db.flush()

        google_connection = self._add_connection()
        other_connection = CalendarConnection(
            user_id=self.user_id,
            provider="other",
            provider_account_id="acct-other",
            access_token="tok-other",
        )
        self.db.add(other_connection)
        self.db.flush()

        api.sync_event_cache(
            self.db,
            self.user_id,
            "google",
            ["primary"],
            WINDOW_START,
            WINDOW_END,
            [
                _event(
                    "g",
                    datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
                    datetime(2026, 3, 3, 11, tzinfo=timezone.utc),
                )
            ],
        )
        api.record_sync_window(self.db, self.user_id, "google", WINDOW_START, WINDOW_END)

        api.ensure_event_cache(
            self.db,
            self.user_id,
            WINDOW_START,
            WINDOW_END,
            [google_connection, other_connection],
        )
        # The Google block survives the second provider's turn through the loop.
        self.assertEqual(
            self._busy(),
            [
                (
                    datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
                    datetime(2026, 3, 3, 11, tzinfo=timezone.utc),
                )
            ],
        )


class DisconnectPurgeTests(CalendarCacheTestCase):
    def test_disconnect_revokes_and_purges_cached_calendar_data(self) -> None:
        self._add_calendar("primary", primary=True)
        self._add_connection()
        api.sync_event_cache(
            self.db,
            self.user_id,
            "google",
            ["primary"],
            WINDOW_START,
            WINDOW_END,
            [
                _event(
                    "a",
                    datetime(2026, 3, 3, 10, tzinfo=timezone.utc),
                    datetime(2026, 3, 3, 11, tzinfo=timezone.utc),
                )
            ],
        )
        api.record_sync_window(self.db, self.user_id, "google", WINDOW_START, WINDOW_END)
        api.refresh_busy_cache(self.db, self.user_id, WINDOW_START, WINDOW_END, ["primary"])
        self.db.flush()
        self.assertTrue(self._cached_event_ids())

        current_user = SimpleNamespace(user_id=self.user_id, email="user@example.com")
        with mock.patch.object(api.google, "revoke_token", return_value=True) as revoke:
            result = api.google_disconnect(db=self.db, current_user=current_user)

        # The grant itself is revoked upstream, not just forgotten locally.
        revoke.assert_called_once_with("ref")
        self.assertEqual(result["revoked"], 1)
        self.assertEqual(result["revoked_upstream"], 1)

        self.assertEqual(self._cached_event_ids(), set())
        self.assertEqual(self._busy(), [])
        self.assertEqual(
            self.db.execute(
                select(ProviderCalendar).where(ProviderCalendar.user_id == self.user_id)
            ).scalars().all(),
            [],
        )
        self.assertEqual(
            self.db.execute(
                select(CalendarSyncState).where(CalendarSyncState.user_id == self.user_id)
            ).scalars().all(),
            [],
        )
        connection = self.db.execute(
            select(CalendarConnection).where(CalendarConnection.user_id == self.user_id)
        ).scalar_one()
        self.assertIsNotNone(connection.revoked_at)
        self.assertIsNone(connection.access_token)
        self.assertIsNone(connection.refresh_token)

    def test_disconnect_keeps_manual_availability_blocks_busy(self) -> None:
        self._add_calendar("primary", primary=True)
        self._add_connection()
        self.db.add(
            AvailabilityBlock(
                user_id=self.user_id,
                start_at=datetime.now(timezone.utc) + timedelta(days=1),
                end_at=datetime.now(timezone.utc) + timedelta(days=1, hours=1),
                type="busy",
            )
        )
        self.db.flush()

        current_user = SimpleNamespace(user_id=self.user_id, email="user@example.com")
        with mock.patch.object(api.google, "revoke_token", return_value=True):
            api.google_disconnect(db=self.db, current_user=current_user)

        # Busy is derived, so the user's own blocks must survive the purge.
        self.assertEqual(len(self._busy()), 1)

    def test_revoked_connections_are_excluded_from_active(self) -> None:
        connection = self._add_connection()
        connection.revoked_at = datetime.now(timezone.utc)
        self.db.flush()
        self.assertEqual(api.active_connections(self.db, self.user_id), [])


class ProviderCalendarRefreshTests(CalendarCacheTestCase):
    def test_user_toggle_survives_a_provider_refresh(self) -> None:
        self._add_calendar("holidays", enabled=False)
        connection = self._add_connection()

        # Google reports this calendar as selected; the user disabled it here.
        with mock.patch.object(
            api.google,
            "list_calendars",
            return_value=[
                {
                    "provider_calendar_id": "holidays",
                    "name": "Holidays",
                    "is_primary": False,
                    "is_enabled": True,
                    "color": "#fff",
                }
            ],
        ):
            api.refresh_provider_calendars(self.db, connection)
        self.db.flush()

        calendar = self.db.execute(
            select(ProviderCalendar).where(
                ProviderCalendar.user_id == self.user_id,
                ProviderCalendar.provider_calendar_id == "holidays",
            )
        ).scalar_one()
        self.assertFalse(calendar.is_enabled)
        self.assertEqual(calendar.name, "Holidays")

    def test_provider_failure_is_swallowed(self) -> None:
        connection = self._add_connection()
        with mock.patch.object(
            api.google, "list_calendars", side_effect=RuntimeError("google down")
        ):
            api.refresh_provider_calendars(self.db, connection)  # must not raise


if __name__ == "__main__":
    unittest.main()
