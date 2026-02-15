import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import NullLogger, REDACTED_VALUE, RunLogger, utc_now_iso


class TestLogUtils(unittest.TestCase):
    def test_utc_now_iso_returns_iso_format_string(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        # Basic ISO format validation
        self.assertRegex(timestamp, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_run_logger_generates_run_id_by_default(self):
        logger = RunLogger()
        self.assertIsNotNone(logger.run_id)
        self.assertTrue(logger.run_id.startswith("run-"))

    def test_run_logger_accepts_custom_run_id(self):
        logger = RunLogger(run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)

    def test_run_logger_text_format_includes_key_fields(self):
        logger = RunLogger(log_format="text")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                repository="acme/repo",
                mode="mirror",
            )

        output = buffer.getvalue()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("mode=mirror", output)

    def test_run_logger_text_format_includes_message_when_present(self):
        logger = RunLogger(log_format="text")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", message="test message here")

        output = buffer.getvalue()
        self.assertIn("- test message here", output)

    def test_run_logger_json_format_outputs_parseable_json(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="github")

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("github", parsed["provider"])

    def test_run_logger_event_returns_record_dict(self):
        logger = RunLogger()
        record = logger.event("test.action", outcome="info", custom_field="value")

        self.assertIsInstance(record, dict)
        self.assertEqual("test.action", record["action"])
        self.assertEqual("info", record["outcome"])
        self.assertEqual("value", record["custom_field"])

    def test_run_logger_sanitizes_token_fields(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", token="secret-token", api_token="another-secret")

        output = buffer.getvalue()
        self.assertNotIn("secret-token", output)
        self.assertNotIn("another-secret", output)
        self.assertIn(REDACTED_VALUE, output)

    def test_run_logger_sanitizes_password_fields(self):
        logger = RunLogger()
        record = logger.event("test.action", password="my-password", user_password="other")

        self.assertEqual(REDACTED_VALUE, record["password"])
        self.assertEqual(REDACTED_VALUE, record["user_password"])

    def test_run_logger_sanitizes_secret_fields(self):
        logger = RunLogger()
        record = logger.event("test.action", secret="my-secret", api_secret="another")

        self.assertEqual(REDACTED_VALUE, record["secret"])
        self.assertEqual(REDACTED_VALUE, record["api_secret"])

    def test_run_logger_sanitizes_ssh_key_path(self):
        logger = RunLogger()
        record = logger.event("test.action", ssh_key_path="/path/to/key")

        self.assertEqual(REDACTED_VALUE, record["ssh_key_path"])

    def test_run_logger_sanitizes_nested_sensitive_fields(self):
        logger = RunLogger()
        record = logger.event(
            "test.action",
            config={"token": "secret", "other": "safe"},
        )

        self.assertEqual(REDACTED_VALUE, record["config"]["token"])
        self.assertEqual("safe", record["config"]["other"])

    def test_run_logger_sanitizes_sensitive_fields_in_lists(self):
        logger = RunLogger()
        record = logger.event("test.action", tokens=["secret1", "secret2"])

        # Lists containing sensitive fields are redacted as a whole
        self.assertEqual(REDACTED_VALUE, record["tokens"])

    def test_run_logger_does_not_sanitize_non_sensitive_fields(self):
        logger = RunLogger()
        record = logger.event(
            "test.action",
            provider="github",
            repository="acme/repo",
            mode="mirror",
        )

        self.assertEqual("github", record["provider"])
        self.assertEqual("acme/repo", record["repository"])
        self.assertEqual("mirror", record["mode"])

    def test_run_logger_filters_none_values(self):
        logger = RunLogger()
        record = logger.event("test.action", field_with_none=None, field_with_value="value")

        self.assertNotIn("field_with_none", record)
        self.assertEqual("value", record["field_with_value"])

    def test_run_logger_supports_custom_log_levels(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", level="WARNING", outcome="warn")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("WARNING", parsed["level"])

    def test_run_logger_writes_to_log_file_when_specified(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="text", log_file=log_path)

            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success")

            logger.close()

            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
                self.assertIn("test.action", content)
                self.assertIn("outcome=success", content)

    def test_run_logger_creates_log_directory_when_needed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "subdir", "logs", "test.log")
            logger = RunLogger(log_file=log_path)
            logger.close()

            self.assertTrue(os.path.exists(os.path.dirname(log_path)))

    def test_run_logger_context_manager_closes_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")

            with RunLogger(log_file=log_path) as logger:
                with redirect_stdout(io.StringIO()):
                    logger.event("test.action", outcome="success")

            # File should be closed now, verify by checking handle is None
            # We can't directly check if file is closed, but we can verify content was written
            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
                self.assertIn("test.action", content)

    def test_run_logger_close_is_idempotent(self):
        logger = RunLogger()
        logger.close()
        logger.close()  # Should not raise

    def test_null_logger_returns_empty_dict_from_event(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="info", field="value")
        self.assertEqual({}, result)

    def test_null_logger_has_text_format(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_null_logger_has_run_id(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()  # Should not raise

    def test_run_logger_json_format_sorts_keys(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", zebra="z", alpha="a", middle="m")

        output = buffer.getvalue()
        # Check that keys appear in sorted order in the JSON string
        self.assertLess(output.index('"action"'), output.index('"alpha"'))
        self.assertLess(output.index('"alpha"'), output.index('"middle"'))

    def test_run_logger_includes_timestamp_in_record(self):
        logger = RunLogger()
        record = logger.event("test.action", outcome="success")

        self.assertIn("timestamp", record)
        self.assertIsInstance(record["timestamp"], str)
        self.assertIn("T", record["timestamp"])


if __name__ == "__main__":
    unittest.main()