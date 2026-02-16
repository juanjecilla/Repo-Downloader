import os
import sys
import unittest
from unittest.mock import patch

from utils import sentry_utils


class _FakeSentrySDK:
    def __init__(self):
        self.init_calls = []
        self.tags = {}
        self.captured = []

    def init(self, **kwargs):
        self.init_calls.append(kwargs)

    def set_tag(self, key, value):
        self.tags[key] = value

    def capture_exception(self, exc):
        self.captured.append(str(exc))


class TestSentryUtils(unittest.TestCase):
    def test_resolve_sentry_settings_from_environment(self):
        with patch.dict(
            os.environ,
            {
                "REPO_DOWNLOADER_SENTRY_DSN": "dsn-value",
                "REPO_DOWNLOADER_SENTRY_ENVIRONMENT": "staging",
                "REPO_DOWNLOADER_SENTRY_RELEASE": "v1.2.3",
            },
            clear=True,
        ):
            settings = sentry_utils.resolve_sentry_settings(args=None)

        self.assertEqual("dsn-value", settings["dsn"])
        self.assertEqual("staging", settings["environment"])
        self.assertEqual("v1.2.3", settings["release"])

    def test_initialize_sentry_skips_when_dsn_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            result = sentry_utils.initialize_sentry(args=None, logger=None)

        self.assertFalse(result["enabled"])

    def test_set_tags_and_capture_exception_when_enabled(self):
        fake_sdk = _FakeSentrySDK()

        with patch.dict(os.environ, {"REPO_DOWNLOADER_SENTRY_DSN": "dsn-value"}, clear=True):
            with patch.dict(sys.modules, {"sentry_sdk": fake_sdk}):
                result = sentry_utils.initialize_sentry(args=None, logger=None)
                sentry_utils.set_sentry_tags(
                    command="backup",
                    provider="github",
                    mode="mirror",
                    run_id="run-123",
                )
                sentry_utils.capture_exception(RuntimeError("boom"))

        self.assertTrue(result["enabled"])
        self.assertEqual("backup", fake_sdk.tags["command"])
        self.assertEqual("github", fake_sdk.tags["provider"])
        self.assertIn("boom", fake_sdk.captured[0])

    def test_before_send_redacts_token_like_message(self):
        event = {
            "message": "authentication failed token=secret-token",
            "exception": {
                "values": [{"value": "authorization: bearer abcdef"}],
            },
        }

        redacted = sentry_utils._before_send(  # pylint: disable=protected-access
            event,
            _hint={},
        )

        self.assertNotIn("secret-token", redacted["message"])
        self.assertNotIn("abcdef", redacted["exception"]["values"][0]["value"])


if __name__ == "__main__":
    unittest.main()
