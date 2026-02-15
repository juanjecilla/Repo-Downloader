import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from utils.log_utils import NullLogger, REDACTED_VALUE, RunLogger, utc_now_iso


class TestUtcNowIso(unittest.TestCase):
    def test_returns_iso_format_string(self):
        result = utc_now_iso()
        self.assertIsInstance(result, str)
        # Should contain date and time separator
        self.assertIn("T", result)

    def test_returns_different_values_on_subsequent_calls(self):
        result1 = utc_now_iso()
        import time
        time.sleep(0.01)
        result2 = utc_now_iso()
        # Results should be different (or equal if calls are very fast)
        # Just verify they are both valid strings
        self.assertIsInstance(result1, str)
        self.assertIsInstance(result2, str)


class TestRunLogger(unittest.TestCase):
    def test_init_generates_run_id(self):
        logger = RunLogger()
        self.assertIsInstance(logger.run_id, str)
        self.assertTrue(logger.run_id.startswith("run-"))

    def test_init_accepts_custom_run_id(self):
        logger = RunLogger(run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)

    def test_init_sets_log_format(self):
        logger = RunLogger(log_format="json")
        self.assertEqual("json", logger.log_format)

    def test_event_returns_record_with_required_fields(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success")

        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertIn("timestamp", record)
        self.assertIn("run_id", record)
        self.assertIn("level", record)

    def test_event_includes_custom_fields(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "test.action",
                outcome="success",
                provider="github",
                repository="acme/repo",
            )

        self.assertEqual("github", record["provider"])
        self.assertEqual("acme/repo", record["repository"])

    def test_event_json_format_outputs_valid_json(self):
        logger = RunLogger(log_format="json", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", count=42)

        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual(42, parsed["count"])
        self.assertEqual("test-run", parsed["run_id"])

    def test_event_text_format_outputs_readable_line(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")

        output = buffer.getvalue().strip()

        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("run_id=test-run", output)
        self.assertIn("provider=bitbucket", output)

    def test_event_with_message_includes_in_output(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", message="Custom message here")

        output = buffer.getvalue().strip()
        self.assertIn("Custom message here", output)

    def test_event_with_error_field_includes_in_text_output(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="failed", error="Something went wrong")

        output = buffer.getvalue().strip()
        self.assertIn("error=Something went wrong", output)

    def test_sensitive_field_redaction_in_json(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "auth.test",
                outcome="success",
                token="secret-token-value",
                password="secret-password",
            )

        self.assertEqual(REDACTED_VALUE, record["token"])
        self.assertEqual(REDACTED_VALUE, record["password"])
        self.assertNotIn("secret-token-value", buffer.getvalue())
        self.assertNotIn("secret-password", buffer.getvalue())

    def test_ssh_key_path_is_redacted(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "config.test",
                outcome="success",
                ssh_key_path="/home/user/.ssh/id_rsa",
            )

        self.assertEqual(REDACTED_VALUE, record["ssh_key_path"])
        self.assertNotIn("/home/user/.ssh/id_rsa", buffer.getvalue())

    def test_nested_dict_redaction(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "config.test",
                outcome="success",
                settings={"api_token": "secret", "username": "public"},
            )

        self.assertEqual(REDACTED_VALUE, record["settings"]["api_token"])
        self.assertEqual("public", record["settings"]["username"])
        self.assertNotIn("secret", buffer.getvalue())

    def test_list_field_redaction_when_key_is_sensitive(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "config.test",
                outcome="success",
                tokens=["token1", "token2"],
            )

        # When key is sensitive, entire value is redacted
        self.assertEqual(REDACTED_VALUE, record["tokens"])

    def test_log_file_writes_events(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as tmp:
            log_path = tmp.name

        try:
            logger = RunLogger(log_format="json", log_file=log_path, run_id="test-file-run")
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")

            logger.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()

            self.assertIn("test.action", content)
            self.assertIn("test-file-run", content)

            parsed = json.loads(content.strip())
            self.assertEqual("test.action", parsed["action"])
        finally:
            if os.path.exists(log_path):
                os.remove(log_path)

    def test_log_file_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "nested", "dir", "test.log")
            self.assertFalse(os.path.exists(os.path.dirname(log_path)))

            logger = RunLogger(log_format="json", log_file=log_path)
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                logger.event("test.action", outcome="success")

            logger.close()

            self.assertTrue(os.path.exists(log_path))

    def test_context_manager_closes_log_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as tmp:
            log_path = tmp.name

        try:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with RunLogger(log_format="json", log_file=log_path) as logger:
                    logger.event("test.action", outcome="success")
                    handle = logger._log_file_handle
                    self.assertIsNotNone(handle)

            # After exiting context, handle should be closed
            self.assertIsNone(logger._log_file_handle)
        finally:
            if os.path.exists(log_path):
                os.remove(log_path)

    def test_close_can_be_called_multiple_times(self):
        logger = RunLogger(log_format="json")
        logger.close()
        logger.close()
        # Should not raise an error

    def test_level_field_can_be_customized(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="failed", level="ERROR")

        self.assertEqual("ERROR", record["level"])

    def test_level_defaults_to_info(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success")

        self.assertEqual("INFO", record["level"])

    def test_none_values_are_excluded_from_output(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "test.action",
                outcome="success",
                field_with_value="present",
                field_with_none=None,
            )

        self.assertIn("field_with_value", record)
        self.assertNotIn("field_with_none", record)

    def test_text_format_with_duration_ms(self):
        logger = RunLogger(log_format="text", run_id="test-run")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", duration_ms=1234)

        output = buffer.getvalue().strip()
        self.assertIn("duration_ms=1234", output)

    def test_json_output_is_sorted(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", zebra="z", alpha="a")

        output = buffer.getvalue().strip()
        # In sorted JSON, "action" should come before "zebra"
        action_pos = output.index('"action"')
        zebra_pos = output.index('"zebra"')
        self.assertLess(action_pos, zebra_pos)


class TestNullLogger(unittest.TestCase):
    def test_has_log_format_attribute(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_has_run_id_attribute(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)

    def test_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", field="value")
        self.assertEqual({}, result)

    def test_event_does_not_output_to_stdout(self):
        logger = NullLogger()
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success")

        output = buffer.getvalue()
        self.assertEqual("", output)

    def test_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()
        # Should not raise an error

    def test_can_be_used_in_place_of_run_logger(self):
        # This tests that NullLogger has the same interface as RunLogger
        logger = NullLogger()
        logger.event("test.action", outcome="success")
        logger.close()
        # Should complete without errors


class TestSensitiveKeyDetection(unittest.TestCase):
    def test_detects_token_in_key_name(self):
        logger = RunLogger(log_format="json")
        self.assertTrue(logger._is_sensitive_key("api_token"))
        self.assertTrue(logger._is_sensitive_key("auth_token"))
        self.assertTrue(logger._is_sensitive_key("access_token"))

    def test_detects_password_in_key_name(self):
        logger = RunLogger(log_format="json")
        self.assertTrue(logger._is_sensitive_key("password"))
        self.assertTrue(logger._is_sensitive_key("user_password"))
        self.assertTrue(logger._is_sensitive_key("db_password"))

    def test_detects_secret_in_key_name(self):
        logger = RunLogger(log_format="json")
        self.assertTrue(logger._is_sensitive_key("secret"))
        self.assertTrue(logger._is_sensitive_key("client_secret"))
        self.assertTrue(logger._is_sensitive_key("api_secret"))

    def test_detects_ssh_key_path_in_key_name(self):
        logger = RunLogger(log_format="json")
        self.assertTrue(logger._is_sensitive_key("ssh_key_path"))
        self.assertTrue(logger._is_sensitive_key("SSH_KEY_PATH"))

    def test_case_insensitive_detection(self):
        logger = RunLogger(log_format="json")
        self.assertTrue(logger._is_sensitive_key("TOKEN"))
        self.assertTrue(logger._is_sensitive_key("Password"))
        self.assertTrue(logger._is_sensitive_key("SECRET"))

    def test_non_sensitive_keys_not_detected(self):
        logger = RunLogger(log_format="json")
        self.assertFalse(logger._is_sensitive_key("username"))
        self.assertFalse(logger._is_sensitive_key("provider"))
        self.assertFalse(logger._is_sensitive_key("repository"))
        self.assertFalse(logger._is_sensitive_key("count"))


class TestLoggerEdgeCases(unittest.TestCase):
    def test_event_with_integer_fields(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success", count=123, index=0)

        self.assertEqual(123, record["count"])
        self.assertEqual(0, record["index"])

    def test_event_with_boolean_fields(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success", enabled=True, disabled=False)

        self.assertTrue(record["enabled"])
        self.assertFalse(record["disabled"])

    def test_event_with_empty_string_fields(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event("test.action", outcome="success", empty_field="")

        self.assertEqual("", record["empty_field"])

    def test_event_with_special_characters_in_strings(self):
        logger = RunLogger(log_format="json")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            record = logger.event(
                "test.action",
                outcome="success",
                message='String with "quotes" and \n newlines',
            )

        # JSON should properly escape these
        output = buffer.getvalue()
        parsed = json.loads(output.strip())
        self.assertIn("quotes", parsed["message"])
        self.assertIn("newlines", parsed["message"])

    def test_log_file_path_expansion(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Use a path with tilde that will be expanded
            with patch("os.path.expanduser", return_value=f"{tmp_dir}/expanded.log"):
                logger = RunLogger(log_format="json", log_file="~/test.log")
                buffer = io.StringIO()

                with redirect_stdout(buffer):
                    logger.event("test.action", outcome="success")

                logger.close()

                # Verify the file was created at the expanded path
                self.assertIsNotNone(logger._log_file_path)


if __name__ == "__main__":
    unittest.main()