import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException

from app.api import deps
from app.api.deps import CurrentUser, get_current_user


class DevAuthFallbackTests(unittest.TestCase):
    """Locks the rule that dev-auth only applies in local mode with the flag on."""

    def test_local_with_flag_returns_dev_user(self) -> None:
        with patch.object(deps.settings, "env", "local"), patch.object(
            deps.settings, "allow_dev_auth", True
        ):
            user = get_current_user(credentials=None)
        self.assertIsInstance(user, CurrentUser)
        self.assertEqual(str(user.user_id), deps.settings.dev_user_id)

    def test_local_without_flag_rejects_missing_credentials(self) -> None:
        with patch.object(deps.settings, "env", "local"), patch.object(
            deps.settings, "allow_dev_auth", False
        ):
            with self.assertRaises(HTTPException) as ctx:
                get_current_user(credentials=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_production_never_uses_dev_auth(self) -> None:
        # Even with the flag on, a non-local env must require real credentials.
        with patch.object(deps.settings, "env", "production"), patch.object(
            deps.settings, "allow_dev_auth", True
        ):
            with self.assertRaises(HTTPException) as ctx:
                get_current_user(credentials=None)
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
