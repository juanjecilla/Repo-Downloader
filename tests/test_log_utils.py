import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import NullLogger, RunLogger, REDACTED_VALUE, utc_now_iso


class TestLogUtils(unittest.TestCase):
    def test_utc_now_iso_returns_iso_timestamp(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        self.assertRegex(timestamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_run_logger_generates_unique_run_id(self):
        logger1 = RunLogger()
        logger2 = RunLogger()
        self.assertNotEqual(logger1.run_id, logger2.run_id)
        self.assertTrue(logger1.run_id.startswith("run-"))
        logger1.close()
        logger2.close()

    def test_run_logger_accepts_custom_run_id(self):
        logger = RunLogger(run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)
        logger.close()

    def test_run_logger_json_format_emits_parseable_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("test-run", parsed["run_id"])
        self.assertEqual("INFO", parsed["level"])
        self.assertEqual("bitbucket", parsed["provider"])
        self.assertIn("timestamp", parsed)

    def test_run_logger_text_format_includes_key_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                level="INFO",
                provider="github",
                repository="acme/example",
                mode="mirror",
            )
        logger.close()

        output = buffer.getvalue().strip()

        self.assertIn("[INFO]", output)
        self.assertIn("repository.start", output)
        self.assertIn("outcome=start", output)
        self.assertIn("run_id=test-run", output)
        self.assertIn("provider=github", output)
        self.assertIn("repository=acme/example", output)
        self.assertIn("mode=mirror", output)

    def test_run_logger_text_format_includes_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event(
                "test.event",
                outcome="info",
                message="Custom message here",
            )
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("- Custom message here", output)

    def test_run_logger_redacts_token_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "test.event",
                outcome="info",
                token="super-secret-token",
                api_token="another-secret",
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertEqual(REDACTED_VALUE, parsed["api_token"])

    def test_run_logger_redacts_password_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "test.event",
                outcome="info",
                password="user-password",
                app_password="bitbucket-app-password",
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["password"])
        self.assertEqual(REDACTED_VALUE, parsed["app_password"])

    def test_run_logger_redacts_secret_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "test.event",
                outcome="info",
                client_secret="oauth-secret",
                secret_key="encryption-key",
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["client_secret"])
        self.assertEqual(REDACTED_VALUE, parsed["secret_key"])

    def test_run_logger_redacts_ssh_key_path_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "test.event",
                outcome="info",
                ssh_key_path="~/.ssh/id_rsa",
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])

    def test_run_logger_redacts_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "test.event",
                outcome="info",
                config={
                    "provider": "github",
                    "token": "secret-token",
                    "ssh_key_path": "~/.ssh/id_rsa",
                },
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("github", parsed["config"]["provider"])
        self.assertEqual(REDACTED_VALUE, parsed["config"]["token"])
        self.assertEqual(REDACTED_VALUE, parsed["config"]["ssh_key_path"])

    def test_run_logger_redacts_sensitive_fields_in_lists(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "test.event",
                outcome="info",
                tokens=["token-one", "token-two"],
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        # When the field name itself is sensitive, the entire value is redacted
        self.assertEqual(REDACTED_VALUE, parsed["tokens"])

    def test_run_logger_writes_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "logs", "test.log")
            logger = RunLogger(log_format="json", log_file=log_file_path, run_id="test-file")
            logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_file_path))
            with open(log_file_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()

            self.assertIn("test.action", content)
            parsed = json.loads(content.strip())
            self.assertEqual("test.action", parsed["action"])
            self.assertEqual("test-file", parsed["run_id"])

    def test_run_logger_appends_to_existing_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "test.log")
            with open(log_file_path, "w", encoding="utf-8") as log_file:
                log_file.write("previous log entry\n")

            logger = RunLogger(log_format="text", log_file=log_file_path, run_id="test-append")
            logger.event("test.action", outcome="success")
            logger.close()

            with open(log_file_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()

            self.assertIn("previous log entry", content)
            self.assertIn("test.action", content)

    def test_run_logger_context_manager_closes_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_format="json", log_file=log_file_path, run_id="test-context") as logger:
                logger.event("test.action", outcome="success")
                self.assertIsNotNone(logger._log_file_handle)

            self.assertIsNone(logger._log_file_handle)
            self.assertTrue(os.path.exists(log_file_path))

    def test_run_logger_close_is_idempotent(self):
        logger = RunLogger(log_format="text")
        logger.close()
        logger.close()

    def test_run_logger_event_returns_record(self):
        logger = RunLogger(log_format="text", run_id="test-return")
        with redirect_stdout(io.StringIO()):
            record = logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
            )
        logger.close()

        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("test-return", record["run_id"])
        self.assertEqual("bitbucket", record["provider"])

    def test_run_logger_text_format_includes_error_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-error")
        with redirect_stdout(buffer):
            logger.event(
                "repository.finish",
                outcome="failed",
                level="ERROR",
                error="Connection timeout",
            )
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("[ERROR]", output)
        self.assertIn("error=Connection timeout", output)

    def test_run_logger_text_format_includes_duration_ms_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-duration")
        with redirect_stdout(buffer):
            logger.event(
                "sync.mirror.update",
                outcome="success",
                duration_ms=1234,
            )
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("duration_ms=1234", output)

    def test_run_logger_omits_none_values(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-none")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                error=None,
                workspace=None,
            )
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertNotIn("error", parsed)
        self.assertNotIn("workspace", parsed)
        self.assertIn("provider", parsed)

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        record = logger.event("test.action", outcome="success", provider="github")
        self.assertEqual({}, record)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()

    def test_null_logger_has_log_format_attribute(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_null_logger_has_run_id_attribute(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)


if __name__ == "__main__":
    unittest.main()