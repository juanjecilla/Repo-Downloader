import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

from utils.log_utils import NullLogger, REDACTED_VALUE, RunLogger, utc_now_iso


class TestUtcNowIso(unittest.TestCase):
    def test_utc_now_iso_returns_valid_iso_format(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        parsed = datetime.fromisoformat(timestamp)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_utc_now_iso_includes_timezone_indicator(self):
        timestamp = utc_now_iso()
        self.assertTrue(timestamp.endswith("+00:00") or "Z" in timestamp or "+00:00" in timestamp)


class TestRunLogger(unittest.TestCase):
    def test_run_logger_generates_run_id_when_not_provided(self):
        logger = RunLogger(log_format="text")
        self.assertIsNotNone(logger.run_id)
        self.assertTrue(logger.run_id.startswith("run-"))
        logger.close()

    def test_run_logger_uses_provided_run_id(self):
        logger = RunLogger(log_format="text", run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)
        logger.close()

    def test_run_logger_json_format_outputs_valid_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", key="value")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("test-run", parsed["run_id"])
        self.assertEqual("value", parsed["key"])

    def test_run_logger_text_format_contains_key_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                provider="bitbucket",
                repository="acme/repo",
            )
        logger.close()

        output = buffer.getvalue()
        self.assertIn("repository.start", output)
        self.assertIn("outcome=start", output)
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("test-run", output)

    def test_run_logger_redacts_sensitive_token_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", token="super-secret-token")
        logger.close()

        output = buffer.getvalue()
        self.assertNotIn("super-secret-token", output)
        parsed = json.loads(output.strip())
        self.assertEqual(REDACTED_VALUE, parsed["token"])

    def test_run_logger_redacts_sensitive_password_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", password="my-password")
        logger.close()

        output = buffer.getvalue()
        self.assertNotIn("my-password", output)
        parsed = json.loads(output.strip())
        self.assertEqual(REDACTED_VALUE, parsed["password"])

    def test_run_logger_redacts_ssh_key_path(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("run.start", outcome="start", ssh_key_path="/home/user/.ssh/id_rsa")
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])

    def test_run_logger_redacts_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event(
                "config.loaded",
                outcome="success",
                config={"api_token": "secret-key", "timeout": 30},
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual(30, parsed["config"]["timeout"])

    def test_run_logger_writes_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "logs", "test.log")
            logger = RunLogger(log_format="json", log_file=log_path, run_id="test-run")
            logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
                parsed = json.loads(content.strip())
                self.assertEqual("test.action", parsed["action"])

    def test_run_logger_creates_log_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "nested", "logs", "test.log")
            logger = RunLogger(log_format="text", log_file=log_path)
            logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_path))

    def test_run_logger_context_manager_closes_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_format="text", log_file=log_path) as logger:
                logger.event("test.action", outcome="success")
            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_event_includes_timestamp(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertIn("timestamp", parsed)
        datetime.fromisoformat(parsed["timestamp"])

    def test_run_logger_event_includes_level(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", level="WARNING")
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("WARNING", parsed["level"])

    def test_run_logger_event_default_level_is_info(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("INFO", parsed["level"])

    def test_run_logger_text_format_includes_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", message="Operation completed")
        logger.close()

        output = buffer.getvalue()
        self.assertIn("- Operation completed", output)

    def test_run_logger_sanitizes_list_with_sensitive_key(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                tokens=["token1", "token2"],
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["tokens"])

    def test_run_logger_preserves_non_sensitive_nested_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                config={"timeout": 30, "retries": 3, "safe_value": "visible"},
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(30, parsed["config"]["timeout"])
        self.assertEqual(3, parsed["config"]["retries"])
        self.assertEqual("visible", parsed["config"]["safe_value"])

    def test_run_logger_omits_none_values_from_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", optional_field=None)
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertNotIn("optional_field", parsed)


class TestNullLogger(unittest.TestCase):
    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", key="value")
        self.assertEqual({}, result)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()

    def test_null_logger_has_default_run_id(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_has_text_log_format(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)


if __name__ == "__main__":
    unittest.main()