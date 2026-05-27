import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from app.api.v1.calendar import _decode_state, _encode_state
from app.providers import google


class StateEncodingTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        user_id = uuid.uuid4()
        encoded = _encode_state(user_id, "https://app.example/return")
        decoded = _decode_state(encoded)
        self.assertEqual(decoded["uid"], str(user_id))
        self.assertEqual(decoded["return_to"], "https://app.example/return")
        self.assertIn("nonce", decoded)

    def test_default_return_to_falls_back(self) -> None:
        user_id = uuid.uuid4()
        encoded = _encode_state(user_id, None)
        decoded = _decode_state(encoded)
        self.assertTrue(decoded["return_to"])


class TokenRefreshTests(unittest.TestCase):
    def test_returns_existing_token_when_no_expiry(self) -> None:
        connection = SimpleNamespace(
            access_token="acc-1",
            refresh_token="ref-1",
            expires_at=None,
        )
        with mock.patch.object(google, "refresh_access_token") as refresh_mock:
            token = google.ensure_fresh_access_token(connection)
            self.assertEqual(token, "acc-1")
            refresh_mock.assert_not_called()

    def test_returns_existing_token_when_not_near_expiry(self) -> None:
        connection = SimpleNamespace(
            access_token="acc-1",
            refresh_token="ref-1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        with mock.patch.object(google, "refresh_access_token") as refresh_mock:
            token = google.ensure_fresh_access_token(connection)
            self.assertEqual(token, "acc-1")
            refresh_mock.assert_not_called()

    def test_refreshes_when_near_expiry(self) -> None:
        connection = SimpleNamespace(
            access_token="acc-old",
            refresh_token="ref-1",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=10),
        )
        with mock.patch.object(
            google,
            "refresh_access_token",
            return_value={"access_token": "acc-new", "expires_in": 3600},
        ) as refresh_mock:
            token = google.ensure_fresh_access_token(connection)
            self.assertEqual(token, "acc-new")
            refresh_mock.assert_called_once_with("ref-1")
            self.assertEqual(connection.access_token, "acc-new")
            self.assertTrue(connection.expires_at > datetime.now(timezone.utc))

    def test_returns_none_when_connection_missing_token(self) -> None:
        self.assertIsNone(google.ensure_fresh_access_token(None))
        connection = SimpleNamespace(access_token=None, refresh_token=None, expires_at=None)
        self.assertIsNone(google.ensure_fresh_access_token(connection))


if __name__ == "__main__":
    unittest.main()
