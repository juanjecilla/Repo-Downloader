import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from utils.log_utils import (
    REDACTED_VALUE,
    SENSITIVE_KEY_PARTS,
    NullLogger,
    RunLogger,
    utc_now_iso,
)


class TestLogUtils(unittest.TestCase):
    def test_utc_now_iso_returns_valid_iso_format(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        self.assertIn("+00:00", timestamp)

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", provider="bitbucket")
        self.assertEqual({}, result)

    def test_null_logger_has_text_log_format(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_null_logger_has_run_id(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()

    def test_run_logger_generates_run_id(self):
        logger = RunLogger()
        self.assertTrue(logger.run_id.startswith("run-"))
        self.assertGreater(len(logger.run_id), 4)

    def test_run_logger_accepts_custom_run_id(self):
        logger = RunLogger(run_id="custom-run-123")
        self.assertEqual("custom-run-123", logger.run_id)

    def test_run_logger_defaults_to_text_format(self):
        logger = RunLogger()
        self.assertEqual("text", logger.log_format)

    def test_run_logger_accepts_json_format(self):
        logger = RunLogger(log_format="json")
        self.assertEqual("json", logger.log_format)

    def test_run_logger_event_returns_record_with_required_fields(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "repository.start",
                outcome="start",
                provider="bitbucket",
                repository="acme/repo",
            )

        self.assertEqual("repository.start", record["action"])
        self.assertEqual("start", record["outcome"])
        self.assertEqual("INFO", record["level"])
        self.assertEqual("test-run", record["run_id"])
        self.assertEqual("bitbucket", record["provider"])
        self.assertEqual("acme/repo", record["repository"])
        self.assertIn("timestamp", record)

    def test_run_logger_event_includes_optional_message(self):
        logger = RunLogger(run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "test.action",
                outcome="info",
                message="Test message content",
            )

        self.assertEqual("Test message content", record["message"])

    def test_run_logger_event_respects_custom_level(self):
        logger = RunLogger(run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="failed", level="ERROR")

        self.assertEqual("ERROR", record["level"])

    def test_run_logger_sanitizes_token_fields(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "auth.check",
                outcome="success",
                token="secret-token-value",
                api_token="another-secret",
            )

        self.assertEqual(REDACTED_VALUE, record["token"])
        self.assertEqual(REDACTED_VALUE, record["api_token"])
        self.assertNotIn("secret-token-value", buffer.getvalue())

    def test_run_logger_sanitizes_password_fields(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "auth.check",
                outcome="success",
                password="my-password",
                app_password="bitbucket-password",
            )

        self.assertEqual(REDACTED_VALUE, record["password"])
        self.assertEqual(REDACTED_VALUE, record["app_password"])

    def test_run_logger_sanitizes_secret_fields(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "auth.check",
                outcome="success",
                secret="my-secret",
                client_secret="oauth-secret",
            )

        self.assertEqual(REDACTED_VALUE, record["secret"])
        self.assertEqual(REDACTED_VALUE, record["client_secret"])

    def test_run_logger_sanitizes_ssh_key_path_fields(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "run.start",
                outcome="start",
                ssh_key_path="/home/user/.ssh/id_rsa",
            )

        self.assertEqual(REDACTED_VALUE, record["ssh_key_path"])

    def test_run_logger_sanitizes_nested_sensitive_fields(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "auth.check",
                outcome="success",
                config={
                    "token": "secret-value",
                    "provider": "bitbucket",
                    "nested": {"api_token": "nested-secret"},
                },
            )

        self.assertEqual(REDACTED_VALUE, record["config"]["token"])
        self.assertEqual("bitbucket", record["config"]["provider"])
        self.assertEqual(REDACTED_VALUE, record["config"]["nested"]["api_token"])

    def test_run_logger_sanitizes_sensitive_values_in_lists(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "auth.check",
                outcome="success",
                ssh_key_path=["/path/one", "/path/two"],
            )

        # The sanitizer redacts the entire field when it's sensitive, not individual list items
        self.assertEqual(REDACTED_VALUE, record["ssh_key_path"])

    def test_run_logger_is_sensitive_key_checks_all_parts(self):
        logger = RunLogger()
        for part in SENSITIVE_KEY_PARTS:
            self.assertTrue(logger._is_sensitive_key(f"some_{part}"))
            self.assertTrue(logger._is_sensitive_key(f"{part}_value"))
            self.assertTrue(logger._is_sensitive_key(part.upper()))

    def test_run_logger_is_sensitive_key_case_insensitive(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("TOKEN"))
        self.assertTrue(logger._is_sensitive_key("Token"))
        self.assertTrue(logger._is_sensitive_key("PASSWORD"))
        self.assertTrue(logger._is_sensitive_key("Password"))

    def test_run_logger_json_format_outputs_valid_json(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                count=42,
            )

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual(42, parsed["count"])

    def test_run_logger_json_format_sorts_keys(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", zebra="last", alpha="first")

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        keys = list(parsed.keys())
        self.assertEqual(keys, sorted(keys))

    def test_run_logger_text_format_includes_key_fields(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                provider="bitbucket",
                repository="acme/repo",
                mode="both",
            )

        output = buffer.getvalue()
        self.assertIn("[INFO]", output)
        self.assertIn("repository.start", output)
        self.assertIn("outcome=start", output)
        self.assertIn("run_id=test-run", output)
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/repo", output)
        self.assertIn("mode=both", output)

    def test_run_logger_text_format_includes_error_field(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event(
                "repository.finish",
                outcome="failed",
                level="ERROR",
                error="Connection timeout",
            )

        output = buffer.getvalue()
        self.assertIn("[ERROR]", output)
        self.assertIn("error=Connection timeout", output)

    def test_run_logger_text_format_includes_duration_ms(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event(
                "sync.mirror.clone",
                outcome="success",
                duration_ms=1234,
            )

        output = buffer.getvalue()
        self.assertIn("duration_ms=1234", output)

    def test_run_logger_text_format_includes_message_at_end(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="info",
                message="This is the message content",
            )

        output = buffer.getvalue()
        self.assertIn("- This is the message content", output)

    def test_run_logger_writes_to_file_when_log_file_provided(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_file, run_id="test-run")
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")

            logger.close()

            self.assertTrue(os.path.exists(log_file))
            with open(log_file, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("test.action", content)
            self.assertIn("success", content)

    def test_run_logger_creates_log_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "logs", "nested", "test.log")
            logger = RunLogger(log_format="text", log_file=log_file)
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")

            logger.close()

            self.assertTrue(os.path.exists(log_file))

    def test_run_logger_expands_tilde_in_log_file_path(self):
        logger = RunLogger(log_file="~/test.log")
        expected = os.path.expanduser("~/test.log")
        self.assertEqual(expected, logger._log_file_path)
        logger.close()

    def test_run_logger_close_closes_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_file=log_file)

            self.assertIsNotNone(logger._log_file_handle)
            logger.close()
            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_close_can_be_called_multiple_times(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_file=log_file)

            logger.close()
            logger.close()

    def test_run_logger_context_manager_closes_on_exit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")

            with RunLogger(log_file=log_file) as logger:
                self.assertIsNotNone(logger._log_file_handle)

            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_sanitize_fields_omits_none_values(self):
        logger = RunLogger()
        sanitized = logger._sanitize_fields({
            "provider": "bitbucket",
            "repository": None,
            "count": 0,
        })
        self.assertIn("provider", sanitized)
        self.assertNotIn("repository", sanitized)
        self.assertIn("count", sanitized)
        self.assertEqual(0, sanitized["count"])

    def test_run_logger_json_output_does_not_include_none_values(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                value=None,
                other="present",
            )

        parsed = json.loads(buffer.getvalue().strip())
        self.assertNotIn("value", parsed)
        self.assertIn("other", parsed)


if __name__ == "__main__":
    unittest.main()