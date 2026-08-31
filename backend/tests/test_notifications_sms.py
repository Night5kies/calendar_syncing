import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import notifications
from app.services.notifications import build_twilio_payload, send_notification


class BuildTwilioPayloadTests(unittest.TestCase):
    def test_builds_url_data_and_auth(self) -> None:
        url, data, auth = build_twilio_payload(
            account_sid="AC123",
            auth_token="secret",
            from_number="+15550000000",
            to="+15551112222",
            body="hello",
        )
        self.assertEqual(url, "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json")
        self.assertEqual(data, {"From": "+15550000000", "To": "+15551112222", "Body": "hello"})
        self.assertEqual(auth, ("AC123", "secret"))


class SendSmsTests(unittest.TestCase):
    def _send(self) -> notifications.DeliveryResult:
        return send_notification(
            channel="sms",
            target="+15551112222",
            subject="Reminder",
            body="respond please",
        )

    def test_file_mode_writes_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(notifications.settings, "sms_mode", "file"), patch.object(
                notifications.settings, "notification_outbox_dir", tmp
            ):
                result = self._send()
            self.assertEqual(result.status, "sent")
            files = list(Path(tmp).glob("sms_*.json"))
            self.assertEqual(len(files), 1)

    def test_twilio_mode_configured_posts_and_reports_sent(self) -> None:
        captured = {}

        class _Resp:
            status_code = 201

            def json(self):
                return {"sid": "SM123"}

        def fake_post(url, data=None, auth=None, timeout=None):
            captured["url"] = url
            captured["data"] = data
            captured["auth"] = auth
            return _Resp()

        with patch.object(notifications.settings, "sms_mode", "twilio"), patch.object(
            notifications.settings, "twilio_account_sid", "AC123"
        ), patch.object(notifications.settings, "twilio_auth_token", "secret"), patch.object(
            notifications.settings, "twilio_from_number", "+15550000000"
        ), patch.object(notifications.httpx, "post", fake_post):
            result = self._send()

        self.assertEqual(result.status, "sent")
        self.assertEqual(captured["auth"], ("AC123", "secret"))
        self.assertEqual(captured["data"]["To"], "+15551112222")

    def test_twilio_mode_unconfigured_reports_failed(self) -> None:
        with patch.object(notifications.settings, "sms_mode", "twilio"), patch.object(
            notifications.settings, "twilio_account_sid", None
        ), patch.object(notifications.settings, "twilio_auth_token", None), patch.object(
            notifications.settings, "twilio_from_number", None
        ):
            result = self._send()
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.detail, "twilio_not_configured")


if __name__ == "__main__":
    unittest.main()
