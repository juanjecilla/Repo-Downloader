import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import REDACTED_VALUE, NullLogger, RunLogger, utc_now_iso


class TestLogUtils(unittest.TestCase):
    def test_utc_now_iso_returns_iso_timestamp(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        self.assertTrue(timestamp.endswith("+00:00") or timestamp.endswith("Z"))

    def test_run_logger_generates_run_id(self):
        logger = RunLogger(log_format="text")
        self.assertIsNotNone(logger.run_id)
        self.assertTrue(logger.run_id.startswith("run-"))

    def test_run_logger_accepts_custom_run_id(self):
        logger = RunLogger(log_format="text", run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)

    def test_run_logger_text_format_outputs_readable_line(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                repository="acme/example",
            )
        output = buffer.getvalue()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/example", output)

    def test_run_logger_json_format_outputs_parseable_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                repository="acme/example",
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("test-run", parsed["run_id"])
        self.assertEqual("bitbucket", parsed["provider"])
        self.assertEqual("acme/example", parsed["repository"])
        self.assertIn("timestamp", parsed)

    def test_run_logger_includes_optional_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", message="Optional message text")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("Optional message text", parsed["message"])

    def test_run_logger_redacts_token_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", token="super-secret-token")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("super-secret-token", buffer.getvalue())

    def test_run_logger_redacts_password_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", password="my-password")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["password"])

    def test_run_logger_redacts_ssh_key_path(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", ssh_key_path="/home/user/.ssh/id_rsa")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])

    def test_run_logger_redacts_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="info",
                config={"api_token": "secret-value", "username": "alice"},
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual("alice", parsed["config"]["username"])

    def test_run_logger_redacts_sensitive_fields_in_list(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="info",
                credentials=[{"api_token": "secret-1"}, {"api_token": "secret-2"}],
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["credentials"][0]["api_token"])
        self.assertEqual(REDACTED_VALUE, parsed["credentials"][1]["api_token"])

    def test_run_logger_writes_to_file_when_log_file_provided(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "logs", "test.log")
            logger = RunLogger(log_format="json", log_file=log_file_path, run_id="file-test")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.isfile(log_file_path))
            with open(log_file_path, "r", encoding="utf-8") as log_file:
                logged_line = log_file.read().strip()
            parsed = json.loads(logged_line)
            self.assertEqual("test.action", parsed["action"])
            self.assertEqual("file-test", parsed["run_id"])

    def test_run_logger_creates_log_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "nested", "logs", "test.log")
            logger = RunLogger(log_format="text", log_file=log_file_path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.isfile(log_file_path))

    def test_run_logger_context_manager_closes_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_format="text", log_file=log_file_path) as logger:
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    logger.event("test.action", outcome="success")
                self.assertIsNotNone(logger._log_file_handle)
            # After exiting context, file handle should be closed
            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_close_is_safe_when_no_file_handle(self):
        logger = RunLogger(log_format="text")
        logger.close()
        logger.close()  # Should not raise

    def test_run_logger_skips_none_values_in_sanitized_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", optional_field=None)
        parsed = json.loads(buffer.getvalue().strip())
        self.assertNotIn("optional_field", parsed)

    def test_run_logger_includes_duration_and_error_in_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="failed",
                level="ERROR",
                duration_ms=1500,
                error="Something went wrong",
            )
        output = buffer.getvalue()
        self.assertIn("[ERROR]", output)
        self.assertIn("duration_ms=1500", output)
        self.assertIn("error=Something went wrong", output)

    def test_run_logger_case_insensitive_sensitive_key_detection(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="info",
                API_TOKEN="secret",
                SSH_KEY_PATH="/path",
                Password="pwd",
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["API_TOKEN"])
        self.assertEqual(REDACTED_VALUE, parsed["SSH_KEY_PATH"])
        self.assertEqual(REDACTED_VALUE, parsed["Password"])

    def test_null_logger_does_not_raise_on_event(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="info", field="value")
        self.assertEqual({}, result)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()

    def test_null_logger_has_log_format_and_run_id_attributes(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)
        self.assertEqual("run-null", logger.run_id)


if __name__ == "__main__":
    unittest.main()