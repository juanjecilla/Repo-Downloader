import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import NullLogger, RunLogger, REDACTED_VALUE, utc_now_iso


class TestLogUtils(unittest.TestCase):
    def test_utc_now_iso_returns_valid_iso_timestamp(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        self.assertTrue(timestamp.endswith("+00:00") or timestamp.endswith("Z"))

    def test_run_logger_generates_run_id_when_not_provided(self):
        logger = RunLogger(log_format="text")
        self.assertTrue(logger.run_id.startswith("run-"))
        self.assertEqual(16, len(logger.run_id))

    def test_run_logger_uses_provided_run_id(self):
        logger = RunLogger(log_format="text", run_id="run-custom-id")
        self.assertEqual("run-custom-id", logger.run_id)

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
        self.assertEqual("INFO", parsed["level"])
        self.assertEqual("bitbucket", parsed["provider"])
        self.assertIn("timestamp", parsed)

    def test_run_logger_text_format_outputs_readable_line(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "repository.finish",
                outcome="success",
                level="INFO",
                provider="bitbucket",
                repository="acme/repo",
                mode="mirror",
            )
        output = buffer.getvalue().strip()

        self.assertIn("[INFO]", output)
        self.assertIn("repository.finish", output)
        self.assertIn("outcome=success", output)
        self.assertIn("run_id=run-test", output)
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("mode=mirror", output)

    def test_run_logger_text_format_includes_message_when_provided(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "run.start",
                outcome="start",
                level="INFO",
                message="Starting backup run",
            )
        output = buffer.getvalue().strip()
        self.assertIn("- Starting backup run", output)

    def test_run_logger_redacts_token_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("auth.check", outcome="success", token="secret-value-123")
        parsed = json.loads(buffer.getvalue().strip())

        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("secret-value-123", buffer.getvalue())

    def test_run_logger_redacts_password_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("auth.check", outcome="success", password="my-password")
        parsed = json.loads(buffer.getvalue().strip())

        self.assertEqual(REDACTED_VALUE, parsed["password"])
        self.assertNotIn("my-password", buffer.getvalue())

    def test_run_logger_redacts_ssh_key_path_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("git.clone", outcome="success", ssh_key_path="/home/user/.ssh/id_rsa")
        parsed = json.loads(buffer.getvalue().strip())

        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])
        self.assertNotIn("/home/user/.ssh/id_rsa", buffer.getvalue())

    def test_run_logger_redacts_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "config.check",
                outcome="success",
                config={"api_token": "secret", "username": "myuser"},
            )
        parsed = json.loads(buffer.getvalue().strip())

        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual("myuser", parsed["config"]["username"])
        self.assertNotIn("secret", buffer.getvalue())

    def test_run_logger_redacts_sensitive_values_in_lists(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "auth.multi",
                outcome="success",
                tokens=["token1", "token2", "token3"],
            )
        parsed = json.loads(buffer.getvalue().strip())

        # List sanitization redacts the entire list as a single value
        self.assertEqual(REDACTED_VALUE, parsed["tokens"])
        self.assertNotIn("token1", buffer.getvalue())

    def test_run_logger_writes_to_file_when_log_file_provided(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_file, run_id="run-test")

            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success")
            logger.close()

            with open(log_file, "r", encoding="utf-8") as handle:
                content = handle.read()
            parsed = json.loads(content.strip())

            self.assertEqual("test.action", parsed["action"])
            self.assertEqual("success", parsed["outcome"])

    def test_run_logger_creates_log_directory_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "logs", "subdir", "test.log")
            self.assertFalse(os.path.exists(os.path.dirname(log_file)))

            logger = RunLogger(log_format="text", log_file=log_file, run_id="run-test")
            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_file))

    def test_run_logger_context_manager_closes_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            with redirect_stdout(io.StringIO()):
                with RunLogger(log_format="text", log_file=log_file) as logger:
                    logger.event("test.action", outcome="success")
                    self.assertIsNotNone(logger._log_file_handle)
            # After exiting context, file handle should be closed
            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_close_is_idempotent(self):
        logger = RunLogger(log_format="text", run_id="run-test")
        logger.close()
        logger.close()  # Should not raise

    def test_run_logger_event_returns_record(self):
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(io.StringIO()):
            record = logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                custom_field="value",
            )

        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("run-test", record["run_id"])
        self.assertEqual("bitbucket", record["provider"])
        self.assertEqual("value", record["custom_field"])
        self.assertIn("timestamp", record)

    def test_run_logger_omits_none_values_from_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", field_with_none=None, field_with_value="x")
        parsed = json.loads(buffer.getvalue().strip())

        self.assertNotIn("field_with_none", parsed)
        self.assertEqual("x", parsed["field_with_value"])

    def test_null_logger_returns_empty_dict_from_event(self):
        logger = NullLogger()
        record = logger.event("test.action", outcome="success", provider="bitbucket")
        self.assertEqual({}, record)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()  # Should not raise

    def test_null_logger_has_run_id_attribute(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_has_log_format_attribute(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_run_logger_includes_duration_ms_in_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("sync.mirror.clone", outcome="success", duration_ms=1234)
        output = buffer.getvalue().strip()
        self.assertIn("duration_ms=1234", output)

    def test_run_logger_includes_error_in_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("repository.finish", outcome="failed", error="connection timeout")
        output = buffer.getvalue().strip()
        self.assertIn("error=connection timeout", output)

    def test_run_logger_handles_special_characters_in_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                message='Message with "quotes" and newlines\n\ttabs',
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertIn("quotes", parsed["message"])
        self.assertIn("\n", parsed["message"])


if __name__ == "__main__":
    unittest.main()