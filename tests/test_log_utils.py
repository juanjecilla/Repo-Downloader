import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from utils.log_utils import NullLogger, RunLogger, REDACTED_VALUE, utc_now_iso


class TestLogUtils(unittest.TestCase):
    def test_utc_now_iso_returns_valid_iso_format(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        self.assertIn("+00:00", timestamp)

    def test_run_logger_generates_run_id_when_not_provided(self):
        logger = RunLogger()
        self.assertIsNotNone(logger.run_id)
        self.assertTrue(logger.run_id.startswith("run-"))
        logger.close()

    def test_run_logger_uses_provided_run_id(self):
        logger = RunLogger(run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)
        logger.close()

    def test_run_logger_json_format_outputs_valid_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", test_field="value")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("value", parsed["test_field"])
        self.assertIn("timestamp", parsed)
        self.assertIn("run_id", parsed)

    def test_run_logger_text_format_outputs_readable_text(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("provider=bitbucket", output)

    def test_run_logger_sanitizes_token_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("auth.init", token="secret-token-value")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("secret-token-value", output)

    def test_run_logger_sanitizes_password_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("auth.init", password="my-password")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(REDACTED_VALUE, parsed["password"])
        self.assertNotIn("my-password", output)

    def test_run_logger_sanitizes_ssh_key_path_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("git.config", ssh_key_path="/home/user/.ssh/id_rsa")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])

    def test_run_logger_sanitizes_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "config.load",
                config={"api_token": "secret", "timeout": 30}
            )
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual(30, parsed["config"]["timeout"])
        self.assertNotIn("secret", output)

    def test_run_logger_sanitizes_list_of_sensitive_values(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "multi.tokens",
                tokens=["token1", "token2"]
            )
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        # When the key name itself is sensitive (contains "token"),
        # the entire value is redacted regardless of type
        self.assertEqual(REDACTED_VALUE, parsed["tokens"])

    def test_run_logger_preserves_non_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "repository.sync",
                repository="acme/repo",
                provider="github",
                mode="mirror",
                duration_ms=1234,
            )
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("acme/repo", parsed["repository"])
        self.assertEqual("github", parsed["provider"])
        self.assertEqual("mirror", parsed["mode"])
        self.assertEqual(1234, parsed["duration_ms"])

    def test_run_logger_includes_message_when_provided(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", message="Custom message")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("Custom message", parsed["message"])

    def test_run_logger_text_format_includes_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", message="Test message")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("- Test message", output)

    def test_run_logger_writes_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_file)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_file))
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
            parsed = json.loads(content.strip())
            self.assertEqual("test.action", parsed["action"])

    def test_run_logger_creates_log_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "subdir", "nested", "test.log")
            logger = RunLogger(log_format="json", log_file=log_file)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_file))

    def test_run_logger_expands_tilde_in_log_file_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("os.path.expanduser", return_value=os.path.join(tmp_dir, "test.log")):
                logger = RunLogger(log_format="json", log_file="~/test.log")
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    logger.event("test.action")
                logger.close()

                expected_path = os.path.join(tmp_dir, "test.log")
                self.assertTrue(os.path.exists(expected_path))

    def test_run_logger_appends_to_existing_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")

            # First logger writes an event
            logger1 = RunLogger(log_format="json", log_file=log_file)
            buffer1 = io.StringIO()
            with redirect_stdout(buffer1):
                logger1.event("first.event")
            logger1.close()

            # Second logger appends another event
            logger2 = RunLogger(log_format="json", log_file=log_file)
            buffer2 = io.StringIO()
            with redirect_stdout(buffer2):
                logger2.event("second.event")
            logger2.close()

            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            self.assertEqual(2, len(lines))
            first = json.loads(lines[0])
            second = json.loads(lines[1])
            self.assertEqual("first.event", first["action"])
            self.assertEqual("second.event", second["action"])

    def test_run_logger_context_manager_closes_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")

            with RunLogger(log_format="json", log_file=log_file) as logger:
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    logger.event("test.event")
                self.assertIsNotNone(logger._log_file_handle)

            # File should be closed after context exit
            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_close_is_idempotent(self):
        logger = RunLogger(log_format="text")
        logger.close()
        logger.close()  # Should not raise

    def test_run_logger_event_returns_record(self):
        logger = RunLogger(log_format="text")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success", field="value")
        logger.close()

        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("value", record["field"])
        self.assertIn("timestamp", record)

    def test_run_logger_filters_none_values_from_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", field1="value", field2=None, field3="other")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("value", parsed["field1"])
        self.assertNotIn("field2", parsed)
        self.assertEqual("other", parsed["field3"])

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", field="value")
        self.assertEqual({}, result)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()  # Should not raise

    def test_null_logger_has_expected_attributes(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)
        self.assertEqual("run-null", logger.run_id)

    def test_run_logger_level_field_in_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="failed", level="ERROR")
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("ERROR", parsed["level"])

    def test_run_logger_text_format_includes_standard_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event(
                "repository.sync",
                outcome="success",
                provider="github",
                repository="acme/repo",
                mode="mirror",
                duration_ms=500,
                error="some error"
            )
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("provider=github", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("mode=mirror", output)
        self.assertIn("duration_ms=500", output)
        self.assertIn("error=some error", output)


if __name__ == "__main__":
    unittest.main()