import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from utils.log_utils import NullLogger, RunLogger, REDACTED_VALUE


class TestRunLogger(unittest.TestCase):
    def test_initialization_with_defaults(self):
        logger = RunLogger()
        self.assertEqual("text", logger.log_format)
        self.assertIsNotNone(logger.run_id)
        self.assertTrue(logger.run_id.startswith("run-"))
        logger.close()

    def test_initialization_with_custom_run_id(self):
        logger = RunLogger(run_id="custom-run-id")
        self.assertEqual("custom-run-id", logger.run_id)
        logger.close()

    def test_initialization_with_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertIsNotNone(logger._log_file_handle)
            logger.close()
            self.assertIsNone(logger._log_file_handle)

    def test_initialization_creates_log_directory_if_needed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "subdir", "nested", "test.log")
            logger = RunLogger(log_file=log_path)
            self.assertTrue(os.path.exists(os.path.dirname(log_path)))
            logger.close()

    def test_context_manager_protocol(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with RunLogger(log_format="json", run_id="test-context") as logger:
                logger.event("test.action", outcome="success")
        output = buffer.getvalue()
        self.assertIn("test.action", output)
        self.assertIn("test-context", output)

    def test_event_includes_required_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-required")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", provider="bitbucket")
        output = buffer.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("test-required", parsed["run_id"])
        self.assertEqual("INFO", parsed["level"])
        self.assertEqual("bitbucket", parsed["provider"])
        self.assertIn("timestamp", parsed)
        logger.close()

    def test_event_with_custom_level(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-level")
        with redirect_stdout(buffer):
            logger.event("test.warning", outcome="warn", level="WARNING")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("WARNING", parsed["level"])
        logger.close()

    def test_event_with_message(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-message")
        with redirect_stdout(buffer):
            logger.event("test.action", outcome="success", message="custom message")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual("custom message", parsed["message"])
        logger.close()

    def test_json_format_outputs_valid_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-json")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                repository="acme/repo",
                mode="mirror",
            )
        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual("test.action", parsed["action"])
        self.assertEqual("bitbucket", parsed["provider"])
        self.assertEqual("acme/repo", parsed["repository"])
        self.assertEqual("mirror", parsed["mode"])
        logger.close()

    def test_text_format_outputs_readable_line(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="test-text")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                repository="acme/repo",
            )
        output = buffer.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("test.action", output)
        self.assertIn("outcome=success", output)
        self.assertIn("run_id=test-text", output)
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/repo", output)
        logger.close()

    def test_sensitive_field_redaction_token(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redact-token")
        with redirect_stdout(buffer):
            logger.event("test.auth", outcome="success", token="super-secret-token")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("super-secret-token", buffer.getvalue())
        logger.close()

    def test_sensitive_field_redaction_password(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redact-password")
        with redirect_stdout(buffer):
            logger.event("test.auth", outcome="success", password="my-password")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["password"])
        logger.close()

    def test_sensitive_field_redaction_ssh_key_path(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redact-ssh")
        with redirect_stdout(buffer):
            logger.event("test.config", outcome="success", ssh_key_path="/home/user/.ssh/id_rsa")
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])
        logger.close()

    def test_sensitive_field_redaction_nested_dict(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redact-nested")
        with redirect_stdout(buffer):
            logger.event(
                "test.auth",
                outcome="success",
                credentials={"api_token": "secret", "username": "user"},
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["credentials"]["api_token"])
        self.assertEqual("user", parsed["credentials"]["username"])
        logger.close()

    def test_sensitive_field_redaction_list_with_sensitive_key(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redact-list")
        with redirect_stdout(buffer):
            logger.event("test.auth", outcome="success", tokens=["token1", "token2"])
        parsed = json.loads(buffer.getvalue().strip())
        # When the key itself is sensitive, the whole value is redacted
        self.assertEqual(REDACTED_VALUE, parsed["tokens"])
        logger.close()

    def test_sensitive_field_redaction_list_with_non_sensitive_key(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-redact-list-items")
        with redirect_stdout(buffer):
            logger.event("test.data", outcome="success", items=["value1", "value2"])
        parsed = json.loads(buffer.getvalue().strip())
        # When the key is not sensitive, list items are preserved
        self.assertEqual(["value1", "value2"], parsed["items"])
        logger.close()

    def test_none_values_filtered_from_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-none-filter")
        with redirect_stdout(buffer):
            logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                error=None,
                repository=None,
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertNotIn("error", parsed)
        self.assertNotIn("repository", parsed)
        self.assertIn("provider", parsed)
        logger.close()

    def test_log_file_writes_events(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="json", log_file=log_path, run_id="test-file-write")

            with redirect_stdout(io.StringIO()):
                logger.event("test.one", outcome="success")
                logger.event("test.two", outcome="success")
            logger.close()

            with open(log_path, "r", encoding="utf-8") as log_file:
                lines = log_file.readlines()
            self.assertEqual(2, len(lines))
            self.assertIn("test.one", lines[0])
            self.assertIn("test.two", lines[1])

    def test_log_file_flushes_after_each_event(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test-flush.log")
            logger = RunLogger(log_format="json", log_file=log_path, run_id="test-flush")

            with redirect_stdout(io.StringIO()):
                logger.event("test.action", outcome="success")

            with open(log_path, "r", encoding="utf-8") as log_file:
                content = log_file.read()
            self.assertIn("test.action", content)
            logger.close()

    def test_expanduser_applies_to_log_file_path(self):
        with patch("os.path.expanduser", return_value="/tmp/expanded/path/test.log") as mock_expand:
            with patch("os.makedirs") as mock_makedirs:
                with patch("builtins.open", create=True) as mock_open:
                    mock_open.return_value.__enter__ = lambda self: self
                    mock_open.return_value.__exit__ = lambda self, *args: None
                    mock_open.return_value.close = lambda: None
                    RunLogger(log_file="~/test.log")
                    mock_expand.assert_called_with("~/test.log")
                    mock_makedirs.assert_called_with("/tmp/expanded/path", exist_ok=True)


class TestNullLogger(unittest.TestCase):
    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("test.action", outcome="success", provider="bitbucket")
        self.assertEqual({}, result)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        logger.close()

    def test_null_logger_has_default_attributes(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)
        self.assertEqual("run-null", logger.run_id)


class TestSensitiveFieldDetection(unittest.TestCase):
    def test_case_insensitive_detection(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="test-case")
        with redirect_stdout(buffer):
            logger.event(
                "test.auth",
                outcome="success",
                Token="secret1",
                PASSWORD="secret2",
                api_secret="secret3",
            )
        parsed = json.loads(buffer.getvalue().strip())
        self.assertEqual(REDACTED_VALUE, parsed["Token"])
        self.assertEqual(REDACTED_VALUE, parsed["PASSWORD"])
        self.assertEqual(REDACTED_VALUE, parsed["api_secret"])
        logger.close()


class TestEventReturn(unittest.TestCase):
    def test_event_returns_sanitized_record(self):
        logger = RunLogger(log_format="json", run_id="test-return")
        with redirect_stdout(io.StringIO()):
            record = logger.event(
                "test.action",
                outcome="success",
                provider="bitbucket",
                token="secret",
            )
        self.assertEqual("test.action", record["action"])
        self.assertEqual("success", record["outcome"])
        self.assertEqual("bitbucket", record["provider"])
        self.assertEqual(REDACTED_VALUE, record["token"])
        logger.close()


if __name__ == "__main__":
    unittest.main()