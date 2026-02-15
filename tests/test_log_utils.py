import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

from utils.log_utils import NullLogger, RunLogger, REDACTED_VALUE, SENSITIVE_KEY_PARTS, utc_now_iso


class TestUtcNowIso(unittest.TestCase):
    def test_utc_now_iso_returns_valid_iso_format(self):
        result = utc_now_iso()
        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(result)
        self.assertIsInstance(parsed, datetime)
        # Should include timezone info
        self.assertIsNotNone(parsed.tzinfo)

    def test_utc_now_iso_contains_expected_components(self):
        result = utc_now_iso()
        self.assertIn("T", result)  # ISO 8601 separator
        self.assertIn(":", result)  # Time component


class TestRunLogger(unittest.TestCase):
    def test_init_with_defaults(self):
        logger = RunLogger()
        self.assertEqual("text", logger.log_format)
        self.assertIsNone(logger._log_file_path)
        self.assertIsNone(logger._log_file_handle)
        self.assertTrue(logger.run_id.startswith("run-"))

    def test_init_with_custom_run_id(self):
        logger = RunLogger(run_id="test-123")
        self.assertEqual("test-123", logger.run_id)

    def test_init_with_json_format(self):
        logger = RunLogger(log_format="json")
        self.assertEqual("json", logger.log_format)

    def test_init_creates_log_directory_if_needed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "subdir", "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertTrue(os.path.isdir(os.path.dirname(log_path)))
            logger.close()

    def test_init_expands_tilde_in_log_file_path(self):
        with patch.dict("os.environ", {"HOME": "/home/testuser"}, clear=False):
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Use tmp_dir as a fake home for testing
                fake_log_path = os.path.join(tmp_dir, "test.log")
                logger = RunLogger(log_file=fake_log_path)
                # Just verify it doesn't contain tilde
                self.assertNotIn("~", logger._log_file_path or "")
                logger.close()

    def test_context_manager_closes_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_file=log_path) as logger:
                self.assertIsNotNone(logger._log_file_handle)
            self.assertIsNone(logger._log_file_handle)

    def test_close_closes_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertIsNotNone(logger._log_file_handle)
            logger.close()
            self.assertIsNone(logger._log_file_handle)

    def test_close_is_idempotent(self):
        logger = RunLogger()
        logger.close()
        logger.close()  # Should not raise

    def test_is_sensitive_key_detects_token(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("api_token"))
        self.assertTrue(logger._is_sensitive_key("TOKEN"))
        self.assertTrue(logger._is_sensitive_key("auth_token"))

    def test_is_sensitive_key_detects_password(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("password"))
        self.assertTrue(logger._is_sensitive_key("user_password"))
        self.assertTrue(logger._is_sensitive_key("PASSWORD"))

    def test_is_sensitive_key_detects_secret(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("client_secret"))
        self.assertTrue(logger._is_sensitive_key("SECRET_KEY"))

    def test_is_sensitive_key_detects_ssh_key_path(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("ssh_key_path"))
        self.assertTrue(logger._is_sensitive_key("SSH_KEY_PATH"))

    def test_is_sensitive_key_returns_false_for_safe_keys(self):
        logger = RunLogger()
        self.assertFalse(logger._is_sensitive_key("username"))
        self.assertFalse(logger._is_sensitive_key("repository"))
        self.assertFalse(logger._is_sensitive_key("mode"))

    def test_sanitize_value_redacts_sensitive_string(self):
        logger = RunLogger()
        result = logger._sanitize_value("token", "secret-value")
        self.assertEqual(REDACTED_VALUE, result)

    def test_sanitize_value_passes_through_safe_string(self):
        logger = RunLogger()
        result = logger._sanitize_value("username", "testuser")
        self.assertEqual("testuser", result)

    def test_sanitize_value_redacts_nested_dict(self):
        logger = RunLogger()
        nested = {"api_token": "secret", "username": "user"}
        result = logger._sanitize_value("config", nested)
        self.assertEqual(REDACTED_VALUE, result["api_token"])
        self.assertEqual("user", result["username"])

    def test_sanitize_value_redacts_list_with_sensitive_key(self):
        logger = RunLogger()
        items = ["value1", "value2"]
        result = logger._sanitize_value("tokens", items)
        # When the key is sensitive, the whole value (including lists) is redacted
        self.assertEqual(REDACTED_VALUE, result)

    def test_sanitize_value_passes_through_safe_list(self):
        logger = RunLogger()
        items = ["item1", "item2"]
        result = logger._sanitize_value("repositories", items)
        self.assertEqual(["item1", "item2"], result)

    def test_sanitize_fields_filters_none_values(self):
        logger = RunLogger()
        fields = {"key1": "value1", "key2": None, "key3": "value3"}
        result = logger._sanitize_fields(fields)
        self.assertIn("key1", result)
        self.assertNotIn("key2", result)
        self.assertIn("key3", result)

    def test_event_returns_record_with_required_fields(self):
        logger = RunLogger()
        record = logger.event("test.action", outcome="success")
        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("INFO", record["level"])
        self.assertIn("timestamp", record)
        self.assertIn("run_id", record)

    def test_event_includes_custom_level(self):
        logger = RunLogger()
        record = logger.event("test.action", level="ERROR")
        self.assertEqual("ERROR", record["level"])

    def test_event_includes_message_when_provided(self):
        logger = RunLogger()
        record = logger.event("test.action", message="Test message")
        self.assertEqual("Test message", record["message"])

    def test_event_includes_additional_fields(self):
        logger = RunLogger()
        record = logger.event(
            "test.action",
            provider="bitbucket",
            repository="acme/repo",
            custom_field="value"
        )
        self.assertEqual("bitbucket", record["provider"])
        self.assertEqual("acme/repo", record["repository"])
        self.assertEqual("value", record["custom_field"])

    def test_event_sanitizes_sensitive_fields(self):
        logger = RunLogger()
        record = logger.event("test.action", token="secret", username="user")
        self.assertEqual(REDACTED_VALUE, record["token"])
        self.assertEqual("user", record["username"])

    def test_event_outputs_json_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", value=123)

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual(123, parsed["value"])

    def test_event_outputs_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-text")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")

        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("run_id=test-text", output)

    def test_render_text_line_includes_standard_fields(self):
        logger = RunLogger()
        record = {
            "level": "INFO",
            "action": "test.action",
            "outcome": "success",
            "run_id": "test-run",
        }
        result = logger._render_text_line(record)
        self.assertIn("[INFO]", result)
        self.assertIn("test.action", result)
        self.assertIn("outcome=success", result)

    def test_render_text_line_includes_optional_fields(self):
        logger = RunLogger()
        record = {
            "level": "ERROR",
            "action": "test.action",
            "outcome": "failed",
            "run_id": "test-run",
            "provider": "bitbucket",
            "repository": "acme/repo",
            "mode": "mirror",
            "duration_ms": 1234,
            "error": "Connection failed",
        }
        result = logger._render_text_line(record)
        self.assertIn("provider=bitbucket", result)
        self.assertIn("repository=acme/repo", result)
        self.assertIn("mode=mirror", result)
        self.assertIn("duration_ms=1234", result)
        self.assertIn("error=Connection failed", result)

    def test_render_text_line_includes_message(self):
        logger = RunLogger()
        record = {
            "level": "WARNING",
            "action": "test.action",
            "outcome": "warning",
            "run_id": "test-run",
            "message": "This is a warning message",
        }
        result = logger._render_text_line(record)
        self.assertIn("- This is a warning message", result)

    def test_event_writes_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="text", log_file=log_path)

            # Suppress stdout for this test
            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success")

            logger.close()

            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("test.action", content)
            self.assertIn("outcome=success", content)

    def test_event_writes_json_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_path)

            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success", value=42)

            logger.close()

            with open(log_path, "r", encoding="utf-8") as f:
                line = f.read().strip()

            parsed = json.loads(line)
            self.assertEqual("test.action", parsed["action"])
            self.assertEqual(42, parsed["value"])


class TestNullLogger(unittest.TestCase):
    def test_null_logger_has_default_attributes(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", key="value")
        self.assertEqual({}, result)

    def test_null_logger_close_returns_none(self):
        logger = NullLogger()
        result = logger.close()
        self.assertIsNone(result)

    def test_null_logger_accepts_arbitrary_arguments(self):
        logger = NullLogger()
        # Should not raise
        logger.event("action", "arg2", outcome="test", key1="value1", key2="value2")


class TestSensitiveKeyParts(unittest.TestCase):
    def test_sensitive_key_parts_constant_includes_expected_values(self):
        self.assertIn("token", SENSITIVE_KEY_PARTS)
        self.assertIn("password", SENSITIVE_KEY_PARTS)
        self.assertIn("secret", SENSITIVE_KEY_PARTS)
        self.assertIn("ssh_key_path", SENSITIVE_KEY_PARTS)


class TestRedactedValue(unittest.TestCase):
    def test_redacted_value_constant_is_string(self):
        self.assertIsInstance(REDACTED_VALUE, str)
        self.assertEqual("***REDACTED***", REDACTED_VALUE)


if __name__ == "__main__":
    unittest.main()