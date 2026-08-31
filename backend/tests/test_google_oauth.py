import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from app.api.v1.calendar import (
    _b64encode,
    _decode_state,
    _encode_state,
    sanitize_return_to,
)
from app.core.config import settings
from app.providers import google


class StateEncodingTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        user_id = uuid.uuid4()
        return_to = f"{settings.app_base_url}/settings"
        encoded = _encode_state(user_id, return_to)
        decoded = _decode_state(encoded)
        self.assertEqual(decoded["uid"], str(user_id))
        self.assertEqual(decoded["return_to"], return_to)
        self.assertIn("nonce", decoded)

    def test_default_return_to_falls_back(self) -> None:
        user_id = uuid.uuid4()
        encoded = _encode_state(user_id, None)
        decoded = _decode_state(encoded)
        self.assertTrue(decoded["return_to"])

    def test_unsigned_state_is_rejected(self) -> None:
        """A bare base64 payload is exactly the forgery the signature prevents."""
        import json

        forged = _b64encode(
            json.dumps(
                {
                    "uid": str(uuid.uuid4()),
                    "nonce": "x",
                    "iat": int(datetime.now(timezone.utc).timestamp()),
                    "return_to": settings.app_base_url,
                }
            ).encode()
        )
        with self.assertRaises(ValueError):
            _decode_state(forged)

    def test_tampered_uid_is_rejected(self) -> None:
        """Swapping the victim's id into a validly signed state must not verify."""
        import json

        attacker_state = _encode_state(uuid.uuid4(), None)
        payload, _, signature = attacker_state.partition(".")
        import base64

        raw = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        raw["uid"] = str(uuid.uuid4())
        tampered = _b64encode(json.dumps(raw).encode())
        with self.assertRaises(ValueError):
            _decode_state(f"{tampered}.{signature}")

    def test_expired_state_is_rejected(self) -> None:
        user_id = uuid.uuid4()
        stale = datetime.now(timezone.utc) - timedelta(
            seconds=settings.oauth_state_ttl_seconds + 60
        )
        with mock.patch("app.api.v1.calendar.datetime") as clock:
            clock.now.return_value = stale
            encoded = _encode_state(user_id, None)
        with self.assertRaises(ValueError):
            _decode_state(encoded)


class ReturnToSanitizationTests(unittest.TestCase):
    def test_allows_configured_origin(self) -> None:
        target = f"{settings.app_base_url}/create"
        self.assertEqual(sanitize_return_to(target), target)

    def test_rejects_foreign_origin(self) -> None:
        self.assertEqual(
            sanitize_return_to("https://evil.example/steal"), settings.app_base_url
        )

    def test_rejects_relative_and_scheme_relative_targets(self) -> None:
        self.assertEqual(sanitize_return_to("/create"), settings.app_base_url)
        self.assertEqual(sanitize_return_to("//evil.example"), settings.app_base_url)


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

    def test_naive_expiry_does_not_raise(self) -> None:
        connection = SimpleNamespace(
            access_token="acc-1",
            refresh_token="ref-1",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        )
        self.assertEqual(google.ensure_fresh_access_token(connection), "acc-1")

    def test_returns_none_when_connection_missing_token(self) -> None:
        self.assertIsNone(google.ensure_fresh_access_token(None))
        connection = SimpleNamespace(access_token=None, refresh_token=None, expires_at=None)
        self.assertIsNone(google.ensure_fresh_access_token(connection))


if __name__ == "__main__":
    unittest.main()
