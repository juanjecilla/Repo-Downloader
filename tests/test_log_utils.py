import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from utils.log_utils import REDACTED_VALUE, SENSITIVE_KEY_PARTS, NullLogger, RunLogger, utc_now_iso


class TestUtcNowIso(unittest.TestCase):
    def test_utc_now_iso_returns_iso_format(self):
        timestamp = utc_now_iso()
        self.assertIsInstance(timestamp, str)
        self.assertIn("T", timestamp)
        self.assertTrue(timestamp.endswith("+00:00") or timestamp.endswith("Z"))

    def test_utc_now_iso_is_current_time(self):
        import time
        from datetime import datetime, timezone

        before = datetime.now(timezone.utc)
        time.sleep(0.001)
        timestamp_str = utc_now_iso()
        time.sleep(0.001)
        after = datetime.now(timezone.utc)

        timestamp = datetime.fromisoformat(timestamp_str)
        self.assertGreater(timestamp, before)
        self.assertLess(timestamp, after)


class TestRunLoggerInit(unittest.TestCase):
    def test_run_logger_default_format_is_text(self):
        logger = RunLogger()
        self.assertEqual("text", logger.log_format)
        logger.close()

    def test_run_logger_accepts_json_format(self):
        logger = RunLogger(log_format="json")
        self.assertEqual("json", logger.log_format)
        logger.close()

    def test_run_logger_generates_run_id_if_not_provided(self):
        logger = RunLogger()
        self.assertTrue(logger.run_id.startswith("run-"))
        self.assertEqual(16, len(logger.run_id))
        logger.close()

    def test_run_logger_accepts_custom_run_id(self):
        logger = RunLogger(run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)
        logger.close()

    def test_run_logger_creates_log_file_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "nested", "dir", "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertTrue(os.path.exists(os.path.dirname(log_path)))
            logger.close()

    def test_run_logger_expands_tilde_in_log_file_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            expanded_path = os.path.join(tmp_dir, "test.log")
            with patch("os.path.expanduser", return_value=expanded_path):
                logger = RunLogger(log_file="~/test.log")
                self.assertTrue(os.path.exists(expanded_path))
                logger.close()

    def test_run_logger_opens_log_file_in_append_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger1 = RunLogger(log_file=log_path)
            logger1.event("test.action", outcome="success")
            logger1.close()

            logger2 = RunLogger(log_file=log_path)
            logger2.event("test.action2", outcome="success")
            logger2.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                lines = log_file.readlines()
            self.assertEqual(2, len(lines))


class TestRunLoggerContextManager(unittest.TestCase):
    def test_run_logger_can_be_used_as_context_manager(self):
        with RunLogger() as logger:
            self.assertIsInstance(logger, RunLogger)

    def test_run_logger_closes_file_on_exit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_file=log_path) as logger:
                logger.event("test.action", outcome="success")
                self.assertIsNotNone(logger._log_file_handle)

            self.assertIsNone(logger._log_file_handle)


class TestRunLoggerSensitiveKeys(unittest.TestCase):
    def test_is_sensitive_key_detects_token(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("token"))
        self.assertTrue(logger._is_sensitive_key("api_token"))
        self.assertTrue(logger._is_sensitive_key("access_token"))
        logger.close()

    def test_is_sensitive_key_detects_password(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("password"))
        self.assertTrue(logger._is_sensitive_key("user_password"))
        logger.close()

    def test_is_sensitive_key_detects_secret(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("secret"))
        self.assertTrue(logger._is_sensitive_key("client_secret"))
        logger.close()

    def test_is_sensitive_key_detects_ssh_key_path(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("ssh_key_path"))
        logger.close()

    def test_is_sensitive_key_case_insensitive(self):
        logger = RunLogger()
        self.assertTrue(logger._is_sensitive_key("TOKEN"))
        self.assertTrue(logger._is_sensitive_key("PASSWORD"))
        self.assertTrue(logger._is_sensitive_key("Secret"))
        logger.close()

    def test_is_sensitive_key_returns_false_for_normal_keys(self):
        logger = RunLogger()
        self.assertFalse(logger._is_sensitive_key("provider"))
        self.assertFalse(logger._is_sensitive_key("repository"))
        self.assertFalse(logger._is_sensitive_key("outcome"))
        logger.close()


class TestRunLoggerSanitization(unittest.TestCase):
    def test_sanitize_value_redacts_sensitive_keys(self):
        logger = RunLogger()
        result = logger._sanitize_value("token", "super-secret-value")
        self.assertEqual(REDACTED_VALUE, result)
        logger.close()

    def test_sanitize_value_preserves_normal_values(self):
        logger = RunLogger()
        result = logger._sanitize_value("provider", "bitbucket")
        self.assertEqual("bitbucket", result)
        logger.close()

    def test_sanitize_value_redacts_nested_dict_values(self):
        logger = RunLogger()
        nested = {"api_token": "secret123", "provider": "github"}
        result = logger._sanitize_value("config", nested)
        self.assertEqual(REDACTED_VALUE, result["api_token"])
        self.assertEqual("github", result["provider"])
        logger.close()

    def test_sanitize_value_redacts_list_when_key_is_sensitive(self):
        logger = RunLogger()
        result = logger._sanitize_value("token", ["secret1", "secret2"])
        self.assertEqual(REDACTED_VALUE, result)
        logger.close()

    def test_sanitize_value_processes_list_when_key_is_not_sensitive(self):
        logger = RunLogger()
        result = logger._sanitize_value("items", ["value1", "value2"])
        self.assertEqual(["value1", "value2"], result)
        logger.close()

    def test_sanitize_fields_filters_none_values(self):
        logger = RunLogger()
        fields = {"provider": "bitbucket", "workspace": None, "token": "secret"}
        result = logger._sanitize_fields(fields)
        self.assertNotIn("workspace", result)
        self.assertEqual("bitbucket", result["provider"])
        self.assertEqual(REDACTED_VALUE, result["token"])
        logger.close()


class TestRunLoggerJsonOutput(unittest.TestCase):
    def test_event_outputs_json_with_required_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")
        logger.close()

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("test-run", parsed["run_id"])
        self.assertEqual("INFO", parsed["level"])
        self.assertIn("timestamp", parsed)

    def test_event_includes_custom_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("repo.clone", outcome="success", provider="github", repository="acme/test")
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("github", parsed["provider"])
        self.assertEqual("acme/test", parsed["repository"])

    def test_event_redacts_sensitive_fields_in_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="success", token="secret-token", provider="bitbucket")
        logger.close()

        output = buffer.getvalue()
        parsed = json.loads(output.strip())
        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("secret-token", output)

    def test_event_includes_message_field_when_provided(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("error.detected", outcome="failed", message="Something went wrong")
        logger.close()

        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("Something went wrong", parsed["message"])

    def test_event_sorts_json_keys(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json")
        with redirect_stdout(buffer):
            logger.event("test", outcome="success", zebra="last", alpha="first")
        logger.close()

        output = buffer.getvalue().strip()
        keys = list(json.loads(output).keys())
        sorted_keys = sorted(keys)
        self.assertEqual(sorted_keys, keys)


class TestRunLoggerTextOutput(unittest.TestCase):
    def test_event_outputs_text_with_basic_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-run")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("run_id=test-run", output)

    def test_event_includes_provider_in_text_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("repo.clone", outcome="success", provider="bitbucket")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("provider=bitbucket", output)

    def test_event_includes_repository_in_text_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("repo.clone", outcome="success", repository="acme/test")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("repository=acme/test", output)

    def test_event_includes_mode_in_text_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("sync.start", outcome="start", mode="mirror")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("mode=mirror", output)

    def test_event_includes_duration_in_text_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("sync.finish", outcome="success", duration_ms=1234)
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("duration_ms=1234", output)

    def test_event_includes_error_in_text_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("repo.fail", outcome="failed", error="Connection timeout")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("error=Connection timeout", output)

    def test_event_includes_message_at_end_with_dash_prefix(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("warning.detected", outcome="warning", message="This is a warning")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertTrue(output.endswith("- This is a warning"))

    def test_event_sets_level_in_text_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text")
        with redirect_stdout(buffer):
            logger.event("error.detected", outcome="failed", level="ERROR")
        logger.close()

        output = buffer.getvalue().strip()
        self.assertIn("[ERROR]", output)


class TestRunLoggerFileOutput(unittest.TestCase):
    def test_event_writes_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_path)
            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success", provider="github")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
            parsed = json.loads(content.strip())
            self.assertEqual("test.action", parsed["action"])
            self.assertEqual("github", parsed["provider"])

    def test_event_appends_newline_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_path)
            with redirect_stdout(io.StringIO()):
                logger.event("test.action1", outcome="success")
                logger.event("test.action2", outcome="success")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                lines = log_file.readlines()
            self.assertEqual(2, len(lines))
            self.assertTrue(lines[0].endswith("\n"))
            self.assertTrue(lines[1].endswith("\n"))

    def test_event_flushes_log_file_after_write(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_path)
            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success")

            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
            logger.close()

            self.assertIn("test.action", content)

    def test_close_sets_file_handle_to_none(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertIsNotNone(logger._log_file_handle)
            logger.close()
            self.assertIsNone(logger._log_file_handle)

    def test_close_idempotent_can_be_called_multiple_times(self):
        logger = RunLogger()
        logger.close()
        logger.close()


class TestRunLoggerReturnValue(unittest.TestCase):
    def test_event_returns_record_dict(self):
        logger = RunLogger(log_format="json")
        with redirect_stdout(io.StringIO()):
            record = logger.event("test.action", outcome="success", provider="bitbucket")
        logger.close()

        self.assertIsInstance(record, dict)
        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("bitbucket", record["provider"])


class TestNullLogger(unittest.TestCase):
    def test_null_logger_has_text_format(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_null_logger_has_run_id(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", provider="github")
        self.assertEqual({}, result)

    def test_null_logger_event_accepts_any_arguments(self):
        logger = NullLogger()
        logger.event("action", "positional", outcome="success", any_field="value")

    def test_null_logger_close_returns_none(self):
        logger = NullLogger()
        result = logger.close()
        self.assertIsNone(result)

    def test_null_logger_produces_no_output(self):
        buffer = io.StringIO()
        logger = NullLogger()
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")
        output = buffer.getvalue()
        self.assertEqual("", output)


class TestSensitiveKeyParts(unittest.TestCase):
    def test_sensitive_key_parts_constant_is_tuple(self):
        self.assertIsInstance(SENSITIVE_KEY_PARTS, tuple)

    def test_sensitive_key_parts_includes_expected_values(self):
        expected_parts = ("token", "password", "secret", "ssh_key_path")
        for part in expected_parts:
            self.assertIn(part, SENSITIVE_KEY_PARTS)


if __name__ == "__main__":
    unittest.main()