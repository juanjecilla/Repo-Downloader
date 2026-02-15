import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import NullLogger, RunLogger, REDACTED_VALUE, utc_now_iso


class TestUtcNowIso(unittest.TestCase):
    def test_utc_now_iso_returns_valid_iso_format(self):
        timestamp = utc_now_iso()
        self.assertIn("T", timestamp)
        self.assertIn(":", timestamp)


class TestRunLogger(unittest.TestCase):
    def test_run_logger_generates_run_id_when_not_provided(self):
        logger = RunLogger()
        self.assertIsNotNone(logger.run_id)
        self.assertTrue(logger.run_id.startswith("run-"))

    def test_run_logger_uses_provided_run_id(self):
        logger = RunLogger(run_id="run-custom-123")
        self.assertEqual("run-custom-123", logger.run_id)

    def test_run_logger_defaults_to_text_format(self):
        logger = RunLogger()
        self.assertEqual("text", logger.log_format)

    def test_run_logger_accepts_json_format(self):
        logger = RunLogger(log_format="json")
        self.assertEqual("json", logger.log_format)

    def test_run_logger_event_includes_required_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")

        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("INFO", parsed["level"])
        self.assertEqual("run-test", parsed["run_id"])
        self.assertIn("timestamp", parsed)

    def test_run_logger_event_accepts_custom_level(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="failed", level="ERROR")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("ERROR", parsed["level"])

    def test_run_logger_event_includes_optional_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", message="This is a message")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("This is a message", parsed["message"])

    def test_run_logger_event_includes_additional_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="github",
                repository="acme/repo",
                mode="mirror",
                duration_ms=1234,
            )

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("github", parsed["provider"])
        self.assertEqual("acme/repo", parsed["repository"])
        self.assertEqual("mirror", parsed["mode"])
        self.assertEqual(1234, parsed["duration_ms"])

    def test_run_logger_sanitizes_token_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", token="super-secret-token")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("super-secret-token", buffer.getvalue())

    def test_run_logger_sanitizes_password_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", password="secret-password")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["password"])

    def test_run_logger_sanitizes_ssh_key_path_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", ssh_key_path="/home/.ssh/id_rsa")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])

    def test_run_logger_sanitizes_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                config={"api_token": "secret-token", "url": "https://example.com"},
            )

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual("https://example.com", parsed["config"]["url"])

    def test_run_logger_sanitizes_sensitive_fields_in_list(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                tokens=["token1", "token2"],
            )

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["tokens"])

    def test_run_logger_filters_none_values_from_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                workspace=None,
            )

        parsed = json.loads(buffer.getvalue().strip())
        self.assertIn("provider", parsed)
        self.assertNotIn("workspace", parsed)

    def test_run_logger_text_format_renders_basic_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")

        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("run_id=run-test", output)

    def test_run_logger_text_format_includes_provider_repository_mode(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                provider="github",
                repository="acme/repo",
                mode="mirror",
            )

        output = buffer.getvalue().strip()
        self.assertIn("provider=github", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("mode=mirror", output)

    def test_run_logger_text_format_includes_duration_and_error(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event(
                "repository.finish",
                outcome="failed",
                level="ERROR",
                duration_ms=5000,
                error="Connection timeout",
            )

        output = buffer.getvalue().strip()
        self.assertIn("[ERROR]", output)
        self.assertIn("duration_ms=5000", output)
        self.assertIn("error=Connection timeout", output)

    def test_run_logger_text_format_includes_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", message="This is a test message")

        output = buffer.getvalue().strip()
        self.assertIn("- This is a test message", output)

    def test_run_logger_writes_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "test.log")
            buffer = io.StringIO()

            logger = RunLogger(log_format="json", log_file=log_file_path, run_id="run-test")
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_file_path))
            with open(log_file_path, "r", encoding="utf-8") as f:
                content = f.read()
                parsed = json.loads(content.strip())
                self.assertEqual("test.action", parsed["action"])
                self.assertEqual("success", parsed["outcome"])

    def test_run_logger_creates_log_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "logs", "subdir", "test.log")

            logger = RunLogger(log_format="text", log_file=log_file_path)
            logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_file_path))

    def test_run_logger_appends_to_existing_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "test.log")

            logger1 = RunLogger(log_format="json", log_file=log_file_path, run_id="run-1")
            logger1.event("first.action", outcome="success")
            logger1.close()

            logger2 = RunLogger(log_format="json", log_file=log_file_path, run_id="run-2")
            logger2.event("second.action", outcome="success")
            logger2.close()

            with open(log_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                self.assertEqual(2, len(lines))
                first = json.loads(lines[0])
                second = json.loads(lines[1])
                self.assertEqual("first.action", first["action"])
                self.assertEqual("second.action", second["action"])

    def test_run_logger_context_manager_closes_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "test.log")

            with RunLogger(log_format="json", log_file=log_file_path) as logger:
                logger.event("test.action", outcome="success")

            self.assertTrue(os.path.exists(log_file_path))

    def test_run_logger_close_is_safe_to_call_multiple_times(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_file_path)
            logger.event("test.action", outcome="success")
            logger.close()
            logger.close()

    def test_run_logger_event_returns_event_record(self):
        logger = RunLogger(log_format="json", run_id="run-test")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success", provider="bitbucket")

        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("run-test", record["run_id"])
        self.assertEqual("bitbucket", record["provider"])


class TestNullLogger(unittest.TestCase):
    def test_null_logger_has_default_attributes(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_event_accepts_all_arguments(self):
        logger = NullLogger()
        result = logger.event(
            "test.action",
            outcome="success",
            level="INFO",
            message="test",
            provider="bitbucket",
            repository="acme/repo",
        )
        self.assertEqual({}, result)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()


if __name__ == "__main__":
    unittest.main()