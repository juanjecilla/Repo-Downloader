import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from utils.log_utils import REDACTED_VALUE, NullLogger, RunLogger, utc_now_iso


class TestUtcNowIso(unittest.TestCase):
    def test_returns_iso_format_string(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        self.assertIn(":", timestamp)

    def test_includes_timezone_info(self):
        timestamp = utc_now_iso()
        self.assertTrue(timestamp.endswith("+00:00") or timestamp.endswith("Z"))


class TestRunLogger(unittest.TestCase):
    def test_init_sets_default_log_format(self):
        logger = RunLogger()
        self.assertEqual("text", logger.log_format)

    def test_init_generates_run_id_if_not_provided(self):
        logger = RunLogger()
        self.assertIsInstance(logger.run_id, str)
        self.assertTrue(logger.run_id.startswith("run-"))

    def test_init_uses_provided_run_id(self):
        logger = RunLogger(run_id="custom-run-123")
        self.assertEqual("custom-run-123", logger.run_id)

    def test_init_creates_log_directory_if_needed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "subdir", "logs", "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "subdir", "logs")))
            logger.close()

    def test_init_expands_tilde_in_log_file_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            expanded_path = os.path.join(tmp_dir, "expanded", "log.txt")
            with patch("os.path.expanduser", return_value=expanded_path) as mock_expand:
                logger = RunLogger(log_file="~/log.txt")
                mock_expand.assert_called_with("~/log.txt")
                self.assertTrue(os.path.exists(os.path.dirname(expanded_path)))
                logger.close()

    def test_close_closes_log_file_handle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertIsNotNone(logger._log_file_handle)
            logger.close()
            self.assertIsNone(logger._log_file_handle)

    def test_context_manager_closes_logger(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_file=log_path) as logger:
                self.assertIsNotNone(logger._log_file_handle)
            self.assertIsNone(logger._log_file_handle)

    def test_is_sensitive_key_detects_token(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("token"))
        self.assertTrue(logger._is_sensitive_key("api_token"))
        self.assertTrue(logger._is_sensitive_key("ACCESS_TOKEN"))

    def test_is_sensitive_key_detects_password(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("password"))
        self.assertTrue(logger._is_sensitive_key("app_password"))
        self.assertTrue(logger._is_sensitive_key("PASSWORD_HASH"))

    def test_is_sensitive_key_detects_secret(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("secret"))
        self.assertTrue(logger._is_sensitive_key("client_secret"))
        self.assertTrue(logger._is_sensitive_key("API_SECRET"))

    def test_is_sensitive_key_detects_ssh_key_path(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("ssh_key_path"))
        self.assertTrue(logger._is_sensitive_key("SSH_KEY_PATH"))

    def test_is_sensitive_key_returns_false_for_safe_keys(self):
        logger = RunLogger()
        self.assertFalse(logger._is_sensitive_key("provider"))
        self.assertFalse(logger._is_sensitive_key("repository"))
        self.assertFalse(logger._is_sensitive_key("mode"))
        self.assertFalse(logger._is_sensitive_key("action"))

    def test_sanitize_value_redacts_sensitive_key(self):
        logger = RunLogger()
        result = logger._sanitize_value("token", "super-secret-value")
        self.assertEqual(REDACTED_VALUE, result)

    def test_sanitize_value_preserves_safe_value(self):
        logger = RunLogger()
        result = logger._sanitize_value("provider", "bitbucket")
        self.assertEqual("bitbucket", result)

    def test_sanitize_value_redacts_nested_dict_sensitive_keys(self):
        logger = RunLogger()
        nested = {"provider": "bitbucket", "api_token": "secret"}
        result = logger._sanitize_value("config", nested)
        self.assertEqual("bitbucket", result["provider"])
        self.assertEqual(REDACTED_VALUE, result["api_token"])

    def test_sanitize_value_redacts_list_with_sensitive_key_name(self):
        logger = RunLogger()
        tokens = ["token-1", "token-2"]
        result = logger._sanitize_value("tokens", tokens)
        self.assertEqual(REDACTED_VALUE, result)

    def test_sanitize_value_preserves_list_with_safe_key_name(self):
        logger = RunLogger()
        repos = ["repo-1", "repo-2"]
        result = logger._sanitize_value("repositories", repos)
        self.assertEqual(["repo-1", "repo-2"], result)

    def test_sanitize_fields_removes_none_values(self):
        logger = RunLogger()
        fields = {"provider": "bitbucket", "workspace": None, "mode": "both"}
        result = logger._sanitize_fields(fields)
        self.assertNotIn("workspace", result)
        self.assertIn("provider", result)
        self.assertIn("mode", result)

    def test_sanitize_fields_redacts_sensitive_fields(self):
        logger = RunLogger()
        fields = {"provider": "bitbucket", "token": "secret"}
        result = logger._sanitize_fields(fields)
        self.assertEqual("bitbucket", result["provider"])
        self.assertEqual(REDACTED_VALUE, result["token"])

    def test_render_text_line_formats_basic_event(self):
        logger = RunLogger()
        record = {
            "level": "INFO",
            "action": "repository.start",
            "outcome": "start",
            "run_id": "run-test",
        }
        result = logger._render_text_line(record)
        self.assertIn("[INFO]", result)
        self.assertIn("repository.start", result)
        self.assertIn("outcome=start", result)
        self.assertIn("run_id=run-test", result)

    def test_render_text_line_includes_optional_fields(self):
        logger = RunLogger()
        record = {
            "level": "INFO",
            "action": "sync.mirror.clone",
            "outcome": "success",
            "run_id": "run-test",
            "provider": "bitbucket",
            "repository": "acme/repo",
            "mode": "mirror",
            "duration_ms": 1234,
        }
        result = logger._render_text_line(record)
        self.assertIn("provider=bitbucket", result)
        self.assertIn("repository=acme/repo", result)
        self.assertIn("mode=mirror", result)
        self.assertIn("duration_ms=1234", result)

    def test_render_text_line_includes_message_with_separator(self):
        logger = RunLogger()
        record = {
            "level": "WARNING",
            "action": "auth.token.source",
            "outcome": "fallback",
            "run_id": "run-test",
            "message": "Token env var not set",
        }
        result = logger._render_text_line(record)
        self.assertIn("- Token env var not set", result)

    def test_render_text_line_includes_error_field(self):
        logger = RunLogger()
        record = {
            "level": "ERROR",
            "action": "repository.finish",
            "outcome": "failed",
            "run_id": "run-test",
            "error": "Failed cloning repository",
        }
        result = logger._render_text_line(record)
        self.assertIn("error=Failed cloning repository", result)

    def test_event_outputs_json_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-json-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("run-json-test", parsed["run_id"])
        self.assertEqual("bitbucket", parsed["provider"])

    def test_event_outputs_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-text-test")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")

        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("provider=bitbucket", output)

    def test_event_includes_timestamp(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertIn("timestamp", parsed)
        self.assertIn("T", parsed["timestamp"])

    def test_event_uses_provided_level(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="failed", level="ERROR")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("ERROR", parsed["level"])

    def test_event_includes_message_if_provided(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", message="Custom message")

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("Custom message", parsed["message"])

    def test_event_returns_sanitized_record(self):
        logger = RunLogger(log_format="json")
        with redirect_stdout(io.StringIO()):
            record = logger.event(
                "test.action", outcome="success", token="secret", provider="bitbucket"
            )

        self.assertEqual(REDACTED_VALUE, record["token"])
        self.assertEqual("bitbucket", record["provider"])

    def test_event_writes_to_log_file_if_configured(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_path)
            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
                parsed = json.loads(content.strip())
                self.assertEqual("test.action", parsed["action"])

    def test_event_writes_text_format_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="text", log_file=log_path)
            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success", provider="bitbucket")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
                self.assertIn("test.action", content)
                self.assertIn("outcome=success", content)

    def test_event_appends_to_existing_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")

            logger1 = RunLogger(log_format="json", log_file=log_path)
            with redirect_stdout(io.StringIO()):
                logger1.event("first.action", outcome="success")
            logger1.close()

            logger2 = RunLogger(log_format="json", log_file=log_path)
            with redirect_stdout(io.StringIO()):
                logger2.event("second.action", outcome="success")
            logger2.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                lines = log_file.readlines()
                self.assertEqual(2, len(lines))
                self.assertIn("first.action", lines[0])
                self.assertIn("second.action", lines[1])

    def test_json_output_is_sorted_keys(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", zebra="last", alpha="first")

        output = buffer.getvalue().strip()
        keys = list(json.loads(output).keys())
        self.assertEqual(sorted(keys), keys)


class TestNullLogger(unittest.TestCase):
    def test_has_text_log_format(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_has_null_run_id(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)

    def test_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", provider="bitbucket")
        self.assertEqual({}, result)

    def test_event_accepts_arbitrary_arguments(self):
        logger = NullLogger()
        result = logger.event(
            "test.action",
            outcome="success",
            provider="bitbucket",
            repository="acme/repo",
            custom_field="value",
        )
        self.assertEqual({}, result)

    def test_close_returns_none(self):
        logger = NullLogger()
        result = logger.close()
        self.assertIsNone(result)

    def test_can_be_used_as_drop_in_replacement(self):
        logger = NullLogger()
        try:
            logger.event("test", outcome="success")
            logger.event("test", outcome="failed", error="message")
            logger.close()
        except Exception as exc:
            self.fail(f"NullLogger should not raise exceptions: {exc}")


if __name__ == "__main__":
    unittest.main()