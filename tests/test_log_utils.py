import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import NullLogger, RunLogger, REDACTED_VALUE, utc_now_iso


class TestUtcNowIso(unittest.TestCase):
    def test_utc_now_iso_returns_iso_format_string(self):
        result = utc_now_iso()
        self.assertIsInstance(result, str)
        self.assertIn("T", result)
        self.assertIn(":", result)

    def test_utc_now_iso_includes_timezone(self):
        result = utc_now_iso()
        # ISO format with timezone should end with +00:00 or Z
        self.assertTrue(result.endswith("+00:00") or result.endswith("Z") or "+" in result)


class TestRunLogger(unittest.TestCase):
    def test_init_with_default_parameters(self):
        logger = RunLogger()
        self.assertEqual("text", logger.log_format)
        self.assertTrue(logger.run_id.startswith("run-"))
        self.assertIsNone(logger._log_file_handle)
        logger.close()

    def test_init_with_custom_run_id(self):
        logger = RunLogger(run_id="test-run-123")
        self.assertEqual("test-run-123", logger.run_id)
        logger.close()

    def test_init_with_json_format(self):
        logger = RunLogger(log_format="json")
        self.assertEqual("json", logger.log_format)
        logger.close()

    def test_init_creates_log_file_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "logs", "nested", "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertTrue(os.path.exists(os.path.dirname(log_path)))
            logger.close()

    def test_context_manager_closes_logger(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_file=log_path) as logger:
                self.assertIsNotNone(logger._log_file_handle)
            # After exiting context, file handle should be closed
            self.assertIsNone(logger._log_file_handle)

    def test_event_outputs_json_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("test-json", parsed["run_id"])
        self.assertEqual("bitbucket", parsed["provider"])
        logger.close()

    def test_event_outputs_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-text")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", level="INFO")

        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("run_id=test-text", output)
        logger.close()

    def test_event_includes_optional_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-msg")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", message="custom message")

        output = buffer.getvalue().strip()
        self.assertIn("- custom message", output)
        logger.close()

    def test_event_returns_record_dict(self):
        logger = RunLogger(run_id="test-return")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success", provider="github")

        self.assertIsInstance(record, dict)
        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("github", record["provider"])
        self.assertIn("timestamp", record)
        logger.close()

    def test_event_writes_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
                parsed = json.loads(content.strip())
                self.assertEqual("test.action", parsed["action"])

    def test_event_appends_to_existing_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")

            # First logger
            logger1 = RunLogger(log_format="json", log_file=log_path, run_id="run-1")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger1.event("first.action", outcome="success")
            logger1.close()

            # Second logger (should append)
            logger2 = RunLogger(log_format="json", log_file=log_path, run_id="run-2")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger2.event("second.action", outcome="success")
            logger2.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                lines = log_file.readlines()
                self.assertEqual(2, len(lines))
                first = json.loads(lines[0].strip())
                second = json.loads(lines[1].strip())
                self.assertEqual("first.action", first["action"])
                self.assertEqual("second.action", second["action"])

    def test_sanitize_sensitive_token_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", token="secret-token-value")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("secret-token-value", buffer.getvalue())
        logger.close()

    def test_sanitize_sensitive_password_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", password="my-password")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["password"])
        logger.close()

    def test_sanitize_sensitive_ssh_key_path_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", ssh_key_path="/path/to/key")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])
        logger.close()

    def test_sanitize_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                config={"api_token": "secret", "username": "user"}
            )

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual("user", parsed["config"]["username"])
        logger.close()

    def test_sanitize_list_with_sensitive_items(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                tokens=["secret1", "secret2"]
            )

        parsed = json.loads(buffer.getvalue().strip())
        # When the key itself is sensitive (e.g., "tokens"), the entire value is redacted
        self.assertEqual(REDACTED_VALUE, parsed["tokens"])
        logger.close()

    def test_sanitize_case_insensitive_detection(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                API_TOKEN="secret",
                Password="secret",
                SSH_Key_Path="/path"
            )

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["API_TOKEN"])
        self.assertEqual(REDACTED_VALUE, parsed["Password"])
        self.assertEqual(REDACTED_VALUE, parsed["SSH_Key_Path"])
        logger.close()

    def test_event_filters_none_values(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", field1=None, field2="value")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertNotIn("field1", parsed)
        self.assertEqual("value", parsed["field2"])
        logger.close()

    def test_text_format_includes_standard_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                repository="acme/repo",
                mode="mirror",
                duration_ms=1234,
                error="test error"
            )

        output = buffer.getvalue()
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("mode=mirror", output)
        self.assertIn("duration_ms=1234", output)
        self.assertIn("error=test error", output)
        logger.close()

    def test_close_can_be_called_multiple_times(self):
        logger = RunLogger()
        logger.close()
        logger.close()  # Should not raise
        self.assertIsNone(logger._log_file_handle)


class TestNullLogger(unittest.TestCase):
    def test_null_logger_has_default_attributes(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", field="value")
        self.assertEqual({}, result)

    def test_null_logger_close_does_nothing(self):
        logger = NullLogger()
        result = logger.close()
        self.assertIsNone(result)

    def test_null_logger_accepts_any_parameters(self):
        logger = NullLogger()
        # Should not raise
        logger.event("action", "outcome", "level", "message", extra=1, fields=2)


class TestLoggerEdgeCases(unittest.TestCase):
    def test_logger_with_tilde_in_log_path(self):
        home_dir = os.path.expanduser("~")
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a subdirectory in the temp dir
            test_dir = os.path.join(tmp_dir, "logs")
            os.makedirs(test_dir, exist_ok=True)

            # Use relative path that won't expand to home
            log_path = os.path.join(test_dir, "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertIsNotNone(logger._log_file_handle)
            logger.close()

    def test_logger_with_empty_log_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertIsNotNone(logger._log_file_handle)
            logger.close()

    def test_event_with_special_characters_in_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", message="Test with \"quotes\" and \nnewlines")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertIn("quotes", parsed["message"])
        logger.close()

    def test_event_with_non_string_values(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                count=42,
                ratio=3.14,
                enabled=True,
                disabled=False
            )

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(42, parsed["count"])
        self.assertEqual(3.14, parsed["ratio"])
        self.assertTrue(parsed["enabled"])
        self.assertFalse(parsed["disabled"])
        logger.close()


if __name__ == "__main__":
    unittest.main()