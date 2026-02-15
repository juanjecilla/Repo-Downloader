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
        self.assertIn("+00:00", result)


class TestRunLogger(unittest.TestCase):
    def test_run_logger_generates_run_id_if_not_provided(self):
        logger = RunLogger()
        self.assertTrue(logger.run_id.startswith("run-"))
        self.assertEqual(16, len(logger.run_id))

    def test_run_logger_uses_provided_run_id(self):
        logger = RunLogger(run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)

    def test_event_includes_required_fields(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")
        parsed = json.loads(buffer.getvalue().strip())

        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("test-run", parsed["run_id"])
        self.assertEqual("INFO", parsed["level"])
        self.assertEqual("bitbucket", parsed["provider"])
        self.assertIn("timestamp", parsed)

    def test_event_respects_custom_level(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="failed", level="ERROR")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("ERROR", parsed["level"])

    def test_event_includes_message_when_provided(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="start", message="Starting process")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("Starting process", parsed["message"])

    def test_event_sanitizes_token_field(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", token="super-secret-token")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("super-secret-token", buffer.getvalue())

    def test_event_sanitizes_password_field(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", password="my-password")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["password"])

    def test_event_sanitizes_secret_field(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", api_secret="secret-value")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["api_secret"])

    def test_event_sanitizes_ssh_key_path_field(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("git.clone", outcome="start", ssh_key_path="/home/user/.ssh/id_rsa")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])

    def test_event_sanitizes_nested_dict_with_sensitive_keys(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event(
                "config.load",
                outcome="success",
                config={"username": "user", "api_token": "secret-token", "timeout": 30},
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("user", parsed["config"]["username"])
        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual(30, parsed["config"]["timeout"])

    def test_event_sanitizes_list_with_sensitive_key_name(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("data.list", outcome="start", api_secrets=["public-value", "token-123"])
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["api_secrets"])

    def test_event_does_not_include_none_values(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="start", optional_field=None)
        parsed = json.loads(buffer.getvalue().strip())
        self.assertNotIn("optional_field", parsed)

    def test_text_format_renders_action_and_outcome(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("repository.start", outcome="start")
        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("repository.start", output)
        self.assertIn("outcome=start", output)
        self.assertIn("run_id=test-run", output)

    def test_text_format_includes_provider_repository_mode(self):
        logger = RunLogger(log_format="text")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                provider="bitbucket",
                repository="acme/repo",
                mode="both",
            )
        output = buffer.getvalue().strip()
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("mode=both", output)

    def test_text_format_includes_duration_ms(self):
        logger = RunLogger(log_format="text")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("git.clone", outcome="success", duration_ms=1234)
        output = buffer.getvalue().strip()
        self.assertIn("duration_ms=1234", output)

    def test_text_format_includes_error_field(self):
        logger = RunLogger(log_format="text")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("git.clone", outcome="failed", error="connection timeout")
        output = buffer.getvalue().strip()
        self.assertIn("error=connection timeout", output)

    def test_text_format_includes_message(self):
        logger = RunLogger(log_format="text")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="start", message="Processing started")
        output = buffer.getvalue().strip()
        self.assertIn("- Processing started", output)

    def test_log_file_writes_json_events(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.jsonl")
            logger = RunLogger(log_format="json", log_file=log_path, run_id="file-test")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
            parsed = json.loads(content)
            self.assertEqual("test.action", parsed["action"])
            self.assertEqual("file-test", parsed["run_id"])

    def test_log_file_writes_text_events(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="text", log_file=log_path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
            self.assertIn("test.action", content)
            self.assertIn("outcome=success", content)

    def test_log_file_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "logs", "nested", "test.log")
            logger = RunLogger(log_format="text", log_file=log_path)
            logger.close()
            self.assertTrue(os.path.exists(os.path.dirname(log_path)))

    def test_log_file_appends_to_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("existing line\n")

            logger = RunLogger(log_format="text", log_file=log_path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
            self.assertEqual(2, len(lines))
            self.assertTrue(lines[0].startswith("existing line"))
            self.assertIn("test.action", lines[1])

    def test_context_manager_closes_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_format="text", log_file=log_path) as logger:
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    logger.event("test.action", outcome="success")
                self.assertIsNotNone(logger._log_file_handle)
            self.assertIsNone(logger._log_file_handle)

    def test_close_is_idempotent(self):
        logger = RunLogger(log_format="text")
        logger.close()
        logger.close()

    def test_event_returns_record_dict(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success", provider="bitbucket")
        self.assertIsInstance(record, dict)
        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("bitbucket", record["provider"])


class TestNullLogger(unittest.TestCase):
    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", extra_field="value")
        self.assertEqual({}, result)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()

    def test_null_logger_has_log_format_text(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_null_logger_has_run_id(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)


if __name__ == "__main__":
    unittest.main()