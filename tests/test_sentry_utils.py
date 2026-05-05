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


class _RaisingSentrySDK:
    @staticmethod
    def init(**_kwargs):
        raise ValueError("invalid DSN")


class _MemoryLogger:
    def __init__(self):
        self.events = []

    def event(self, action, outcome="info", level="INFO", message=None, **fields):
        event = {
            "action": action,
            "outcome": outcome,
            "level": level,
            "message": message,
        }
        event.update(fields)
        self.events.append(event)
        return event


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

    def test_initialize_sentry_handles_invalid_dsn(self):
        logger = _MemoryLogger()
        with patch.dict(os.environ, {"REPO_DOWNLOADER_SENTRY_DSN": "bad-dsn"}, clear=True):
            with patch.dict(sys.modules, {"sentry_sdk": _RaisingSentrySDK()}):
                result = sentry_utils.initialize_sentry(args=None, logger=logger)

        self.assertFalse(result["enabled"])
        self.assertEqual("failure", logger.events[0]["outcome"])
        self.assertEqual("init_error", logger.events[0]["source"])
        self.assertIn("invalid DSN", logger.events[0]["message"])

    def test_initialize_sentry_logs_success_when_logger_provided(self):
        logger = _MemoryLogger()
        fake_sdk = _FakeSentrySDK()
        with patch.dict(os.environ, {"REPO_DOWNLOADER_SENTRY_DSN": "dsn-value"}, clear=True):
            with patch.dict(sys.modules, {"sentry_sdk": fake_sdk}):
                result = sentry_utils.initialize_sentry(args=None, logger=logger)

        self.assertTrue(result["enabled"])
        self.assertEqual(1, len(logger.events))
        self.assertEqual("success", logger.events[0]["outcome"])

    def test_initialize_sentry_when_sdk_not_installed(self):
        logger = _MemoryLogger()
        with patch.dict(os.environ, {"REPO_DOWNLOADER_SENTRY_DSN": "dsn-value"}, clear=True):
            with patch.dict(sys.modules, {"sentry_sdk": None}, clear=False):
                result = sentry_utils.initialize_sentry(args=None, logger=logger)

        self.assertFalse(result["enabled"])
        self.assertEqual(0, len(logger.events))

    def test_initialize_sentry_skips_logs_success_without_logger(self):
        fake_sdk = _FakeSentrySDK()
        with patch.dict(os.environ, {"REPO_DOWNLOADER_SENTRY_DSN": "dsn-value"}, clear=True):
            with patch.dict(sys.modules, {"sentry_sdk": fake_sdk}):
                result = sentry_utils.initialize_sentry(args=None, logger=None)

        self.assertTrue(result["enabled"])

    def test_before_send_skips_non_string_message(self):
        event = {"message": 42, "exception": {"values": []}}
        result = sentry_utils._before_send(event, {})  # pylint: disable=protected-access
        self.assertEqual(42, result["message"])

    def test_before_send_skips_non_dict_exception_values(self):
        event = {
            "message": "ok",
            "exception": {"values": ["not-a-dict", 99]},
        }
        result = sentry_utils._before_send(event, {})  # pylint: disable=protected-access
        self.assertEqual(["not-a-dict", 99], result["exception"]["values"])

    def test_before_send_skips_non_string_error_value(self):
        event = {
            "exception": {"values": [{"value": 404}]},
        }
        result = sentry_utils._before_send(event, {})  # pylint: disable=protected-access
        self.assertEqual(404, result["exception"]["values"][0]["value"])

    def test_set_sentry_tags_skips_none_values(self):
        fake_sdk = _FakeSentrySDK()
        with patch.dict(os.environ, {"REPO_DOWNLOADER_SENTRY_DSN": "dsn-value"}, clear=True):
            with patch.dict(sys.modules, {"sentry_sdk": fake_sdk}):
                sentry_utils.initialize_sentry(args=None)
                sentry_utils.set_sentry_tags(command="backup", provider=None)

        self.assertIn("command", fake_sdk.tags)
        self.assertNotIn("provider", fake_sdk.tags)

    def test_set_sentry_tags_no_op_when_sdk_missing(self):
        sentry_utils._SENTRY_STATE["enabled"] = True  # pylint: disable=protected-access
        try:
            with patch.dict(sys.modules, {"sentry_sdk": None}):
                sentry_utils.set_sentry_tags(command="backup")
        finally:
            sentry_utils._SENTRY_STATE["enabled"] = False  # pylint: disable=protected-access

    def test_capture_exception_no_op_when_sdk_missing(self):
        sentry_utils._SENTRY_STATE["enabled"] = True  # pylint: disable=protected-access
        try:
            with patch.dict(sys.modules, {"sentry_sdk": None}):
                sentry_utils.capture_exception(RuntimeError("x"))
        finally:
            sentry_utils._SENTRY_STATE["enabled"] = False  # pylint: disable=protected-access


if __name__ == "__main__":
    unittest.main()
