import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import NullLogger, REDACTED_VALUE, RunLogger, utc_now_iso


class TestUtcNowIso(unittest.TestCase):
    def test_utc_now_iso_returns_iso_format_string(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        self.assertIn("+00:00", timestamp)

    def test_utc_now_iso_is_parseable(self):
        from datetime import datetime
        timestamp = utc_now_iso()
        parsed = datetime.fromisoformat(timestamp)
        self.assertIsNotNone(parsed)


class TestRunLogger(unittest.TestCase):
    def test_run_logger_initializes_with_defaults(self):
        logger = RunLogger()
        self.assertEqual("text", logger.log_format)
        self.assertIsNotNone(logger.run_id)
        self.assertTrue(logger.run_id.startswith("run-"))

    def test_run_logger_accepts_custom_run_id(self):
        logger = RunLogger(run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)

    def test_run_logger_accepts_json_format(self):
        logger = RunLogger(log_format="json")
        self.assertEqual("json", logger.log_format)

    def test_run_logger_event_returns_record_dict(self):
        logger = RunLogger(log_format="json")
        record = logger.event("test.action", outcome="success", provider="bitbucket")

        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("bitbucket", record["provider"])
        self.assertEqual("INFO", record["level"])
        self.assertIn("timestamp", record)
        self.assertIn("run_id", record)

    def test_run_logger_event_json_outputs_valid_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")

        with redirect_stdout(buffer):
            logger.event("repository.start", outcome="start", repository="acme/repo")

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("repository.start", parsed["action"])
        self.assertEqual("acme/repo", parsed["repository"])

    def test_run_logger_event_text_outputs_readable_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-run")

        with redirect_stdout(buffer):
            logger.event(
                "repository.finish",
                outcome="success",
                provider="github",
                repository="acme/repo",
                mode="mirror",
            )

        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("repository.finish", output)
        self.assertIn("outcome=success", output)
        self.assertIn("provider=github", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("mode=mirror", output)

    def test_run_logger_redacts_sensitive_fields(self):
        logger = RunLogger(log_format="json")
        record = logger.event(
            "run.start",
            outcome="start",
            token="super-secret",
            password="my-password",
            api_secret="api-key",
            ssh_key_path="/home/.ssh/id_rsa",
        )

        self.assertEqual(REDACTED_VALUE, record["token"])
        self.assertEqual(REDACTED_VALUE, record["password"])
        self.assertEqual(REDACTED_VALUE, record["api_secret"])
        self.assertEqual(REDACTED_VALUE, record["ssh_key_path"])

    def test_run_logger_redacts_nested_sensitive_fields(self):
        logger = RunLogger(log_format="json")
        record = logger.event(
            "test.event",
            outcome="test",
            config={
                "api_token": "secret-token",
                "user": "testuser",
                "ssh_key_path": "/path/to/key",
            },
        )

        self.assertEqual(REDACTED_VALUE, record["config"]["api_token"])
        self.assertEqual("testuser", record["config"]["user"])
        self.assertEqual(REDACTED_VALUE, record["config"]["ssh_key_path"])

    def test_run_logger_redacts_sensitive_fields_in_lists(self):
        logger = RunLogger(log_format="json")
        record = logger.event(
            "test.event",
            outcome="test",
            credentials=[
                {"name": "cred1", "token": "secret1"},
                {"name": "cred2", "password": "secret2"},
            ],
        )

        self.assertEqual(REDACTED_VALUE, record["credentials"][0]["token"])
        self.assertEqual(REDACTED_VALUE, record["credentials"][1]["password"])
        self.assertEqual("cred1", record["credentials"][0]["name"])

    def test_run_logger_includes_message_field_when_provided(self):
        logger = RunLogger(log_format="json")
        record = logger.event("test.action", outcome="info", message="Custom message")

        self.assertEqual("Custom message", record["message"])

    def test_run_logger_text_format_includes_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="info", message="Test message here")

        output = buffer.getvalue()
        self.assertIn("- Test message here", output)

    def test_run_logger_writes_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_file, run_id="test-file-run")
            logger.event("test.action", outcome="success")
            logger.close()

            with open(log_file, "r", encoding="utf-8") as handle:
                content = handle.read()

            self.assertIn("test.action", content)
            self.assertIn("test-file-run", content)

    def test_run_logger_creates_log_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "logs", "nested", "test.log")
            logger = RunLogger(log_format="json", log_file=log_file)
            logger.event("test.action", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_file))

    def test_run_logger_close_can_be_called_multiple_times(self):
        logger = RunLogger(log_format="text")
        logger.close()
        logger.close()

    def test_run_logger_context_manager_closes_on_exit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "context.log")

            with RunLogger(log_format="json", log_file=log_file) as logger:
                logger.event("test.action", outcome="success")

            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_context_manager_closes_on_exception(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "exception.log")
            logger = None

            try:
                with RunLogger(log_format="json", log_file=log_file) as logger:
                    logger.event("test.action", outcome="start")
                    raise ValueError("test exception")
            except ValueError:
                pass

            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_supports_custom_log_levels(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")

        with redirect_stdout(buffer):
            logger.event("test.warning", outcome="warn", level="WARNING")

        output = buffer.getvalue()
        self.assertIn("[WARNING]", output)

    def test_run_logger_json_format_includes_all_custom_fields(self):
        logger = RunLogger(log_format="json")
        record = logger.event(
            "test.custom",
            outcome="success",
            custom_field="custom_value",
            another_field=123,
            nested={"a": 1, "b": 2},
        )

        self.assertEqual("custom_value", record["custom_field"])
        self.assertEqual(123, record["another_field"])
        self.assertEqual({"a": 1, "b": 2}, record["nested"])

    def test_run_logger_text_format_includes_duration_ms(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", duration_ms=1500)

        output = buffer.getvalue()
        self.assertIn("duration_ms=1500", output)

    def test_run_logger_text_format_includes_error_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="failed", error="Connection timeout")

        output = buffer.getvalue()
        self.assertIn("error=Connection timeout", output)

    def test_run_logger_expands_tilde_in_log_file_path(self):
        original_home = os.environ.get("HOME")
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                os.environ["HOME"] = tmp_dir
                log_file = "~/test.log"
                logger = RunLogger(log_format="json", log_file=log_file)
                logger.event("test.action", outcome="success")
                logger.close()

                expected_path = os.path.join(tmp_dir, "test.log")
                self.assertTrue(os.path.exists(expected_path))
        finally:
            if original_home:
                os.environ["HOME"] = original_home


class TestNullLogger(unittest.TestCase):
    def test_null_logger_has_default_attributes(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", provider="bitbucket")
        self.assertEqual({}, result)

    def test_null_logger_event_accepts_any_arguments(self):
        logger = NullLogger()
        logger.event("action", "positional", outcome="test", custom="field")

    def test_null_logger_close_does_nothing(self):
        logger = NullLogger()
        result = logger.close()
        self.assertIsNone(result)

    def test_null_logger_can_be_used_as_fallback(self):
        def process_with_logger(logger=None):
            logger = logger or NullLogger()
            logger.event("test.action", outcome="success")
            return True

        self.assertTrue(process_with_logger())
        self.assertTrue(process_with_logger(NullLogger()))


if __name__ == "__main__":
    unittest.main()