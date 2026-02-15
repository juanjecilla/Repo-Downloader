import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import REDACTED_VALUE, NullLogger, RunLogger, utc_now_iso


class TestLogUtils(unittest.TestCase):
    def test_utc_now_iso_returns_valid_iso_timestamp(self):
        timestamp = utc_now_iso()
        self.assertIn("T", timestamp)
        self.assertTrue(timestamp.endswith("+00:00") or timestamp.endswith("Z"))

    def test_run_logger_initializes_with_random_run_id(self):
        logger = RunLogger(log_format="text")
        self.assertTrue(logger.run_id.startswith("run-"))
        self.assertEqual(16, len(logger.run_id))
        logger.close()

    def test_run_logger_uses_provided_run_id(self):
        logger = RunLogger(log_format="text", run_id="run-custom-id")
        self.assertEqual("run-custom-id", logger.run_id)
        logger.close()

    def test_run_logger_json_format_outputs_parseable_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("run-test", parsed["run_id"])
        self.assertEqual("bitbucket", parsed["provider"])
        self.assertIn("timestamp", parsed)
        logger.close()

    def test_run_logger_text_format_outputs_readable_text(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                level="INFO",
                provider="github",
                repository="acme/example",
            )
        output = buffer.getvalue().strip()

        self.assertIn("[INFO]", output)
        self.assertIn("repository.start", output)
        self.assertIn("outcome=start", output)
        self.assertIn("run_id=run-test", output)
        self.assertIn("provider=github", output)
        self.assertIn("repository=acme/example", output)
        logger.close()

    def test_run_logger_redacts_sensitive_token_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redaction")
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", token="super-secret-token")
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("super-secret-token", output)
        logger.close()

    def test_run_logger_redacts_sensitive_password_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redaction")
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", password="my-password-123")
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual(REDACTED_VALUE, parsed["password"])
        self.assertNotIn("my-password-123", output)
        logger.close()

    def test_run_logger_redacts_ssh_key_path_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redaction")
        with redirect_stdout(buffer):
            logger.event("git.clone", outcome="start", ssh_key_path="/home/user/.ssh/id_rsa")
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])
        self.assertNotIn("/home/user/.ssh/id_rsa", output)
        logger.close()

    def test_run_logger_redacts_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "config.load",
                outcome="success",
                config={"api_token": "secret-api-token", "workspace": "acme"},
            )
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual("acme", parsed["config"]["workspace"])
        self.assertNotIn("secret-api-token", output)
        logger.close()

    def test_run_logger_redacts_sensitive_fields_in_lists(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "config.load",
                outcome="success",
                tokens=["token-one", "token-two"],
            )
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        # When the key is sensitive, the entire value (including lists) is redacted
        self.assertEqual(REDACTED_VALUE, parsed["tokens"])
        self.assertNotIn("token-one", output)
        self.assertNotIn("token-two", output)
        logger.close()

    def test_run_logger_redacts_items_in_non_sensitive_list(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "config.load",
                outcome="success",
                values=["normal-value", "another-value"],
            )
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        # When the key is not sensitive, list items are passed through as-is
        self.assertEqual(["normal-value", "another-value"], parsed["values"])
        logger.close()

    def test_run_logger_writes_to_file_when_log_file_specified(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="text", log_file=log_path, run_id="run-file")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.event", outcome="success")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                log_content = log_file.read()

            self.assertIn("test.event", log_content)
            self.assertIn("outcome=success", log_content)
            self.assertIn("run-file", log_content)

    def test_run_logger_creates_log_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "nested", "dir", "test.log")
            logger = RunLogger(log_format="text", log_file=log_path, run_id="run-file")
            logger.event("test.event", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_path))

    def test_run_logger_context_manager_closes_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_format="text", log_file=log_path, run_id="run-ctx") as logger:
                logger.event("test.event", outcome="success")
                self.assertIsNotNone(logger._log_file_handle)

            with open(log_path, "r", encoding="utf-8") as log_file:
                log_content = log_file.read()
            self.assertIn("test.event", log_content)

    def test_run_logger_includes_optional_message_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", message="Custom message here")
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual("Custom message here", parsed["message"])
        logger.close()

    def test_run_logger_text_format_includes_message_with_prefix(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", message="Custom message here")
        output = buffer.getvalue().strip()

        self.assertIn("- Custom message here", output)
        logger.close()

    def test_run_logger_omits_none_values_from_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", optional_field=None)
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertNotIn("optional_field", parsed)
        logger.close()

    def test_run_logger_event_returns_sanitized_record(self):
        logger = RunLogger(log_format="text", run_id="run-test")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success", token="secret")

        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual(REDACTED_VALUE, record["token"])
        logger.close()

    def test_run_logger_handles_error_field_in_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "repository.finish",
                outcome="failed",
                level="ERROR",
                error="Connection timeout",
            )
        output = buffer.getvalue().strip()

        self.assertIn("[ERROR]", output)
        self.assertIn("error=Connection timeout", output)
        logger.close()

    def test_run_logger_handles_duration_ms_field_in_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("sync.mirror.clone", outcome="success", duration_ms=1234)
        output = buffer.getvalue().strip()

        self.assertIn("duration_ms=1234", output)
        logger.close()

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", field="value")
        self.assertEqual({}, result)

    def test_null_logger_close_returns_none(self):
        logger = NullLogger()
        result = logger.close()
        self.assertIsNone(result)

    def test_null_logger_has_log_format_and_run_id_attributes(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)
        self.assertEqual("run-null", logger.run_id)

    def test_run_logger_sanitizes_secret_in_nested_dict(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                credentials={"username": "user", "secret_key": "my-secret"},
            )
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual("user", parsed["credentials"]["username"])
        self.assertEqual(REDACTED_VALUE, parsed["credentials"]["secret_key"])
        self.assertNotIn("my-secret", output)
        logger.close()

    def test_run_logger_case_insensitive_sensitive_key_detection(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                API_TOKEN="secret",
                SSH_KEY_PATH="/key",
                User_Password="pass",
            )
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual(REDACTED_VALUE, parsed["API_TOKEN"])
        self.assertEqual(REDACTED_VALUE, parsed["SSH_KEY_PATH"])
        self.assertEqual(REDACTED_VALUE, parsed["User_Password"])
        logger.close()


if __name__ == "__main__":
    unittest.main()