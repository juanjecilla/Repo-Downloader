import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

from utils.log_utils import NullLogger, RunLogger, REDACTED_VALUE, SENSITIVE_KEY_PARTS


class TestLogUtils(unittest.TestCase):
    def test_run_logger_generates_unique_run_id(self):
        logger1 = RunLogger()
        logger2 = RunLogger()
        self.assertIsNotNone(logger1.run_id)
        self.assertIsNotNone(logger2.run_id)
        self.assertNotEqual(logger1.run_id, logger2.run_id)
        logger1.close()
        logger2.close()

    def test_run_logger_accepts_custom_run_id(self):
        logger = RunLogger(run_id="custom-run-123")
        self.assertEqual("custom-run-123", logger.run_id)
        logger.close()

    def test_run_logger_text_format_emits_readable_output(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                provider="bitbucket",
                repository="acme/example",
                mode="both",
            )
        output = buffer.getvalue().strip()
        logger.close()

        self.assertIn("[INFO]", output)
        self.assertIn("repository.start", output)
        self.assertIn("outcome=start", output)
        self.assertIn("run_id=run-test", output)
        self.assertIn("provider=bitbucket", output)
        self.assertIn("repository=acme/example", output)
        self.assertIn("mode=both", output)

    def test_run_logger_json_format_emits_parseable_json(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test-json")
        with redirect_stdout(buffer):
            logger.event(
                "sync.mirror.clone",
                outcome="success",
                provider="github",
                repository="org/repo",
                duration_ms=1234,
            )
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual("sync.mirror.clone", parsed["action"])
        self.assertEqual("success", parsed["outcome"])
        self.assertEqual("run-test-json", parsed["run_id"])
        self.assertEqual("github", parsed["provider"])
        self.assertEqual("org/repo", parsed["repository"])
        self.assertEqual(1234, parsed["duration_ms"])
        self.assertIn("timestamp", parsed)

    def test_run_logger_redacts_token_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redact")
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", token="super-secret-value")
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertNotIn("super-secret-value", buffer.getvalue())

    def test_run_logger_redacts_password_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redact-pw")
        with redirect_stdout(buffer):
            logger.event("auth.start", outcome="start", password="secret-password")
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual(REDACTED_VALUE, parsed["password"])
        self.assertNotIn("secret-password", buffer.getvalue())

    def test_run_logger_redacts_ssh_key_path_field(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-redact-ssh")
        with redirect_stdout(buffer):
            logger.event("run.start", outcome="start", ssh_key_path="/home/user/.ssh/id_rsa")
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])
        self.assertNotIn("/home/user/.ssh/id_rsa", buffer.getvalue())

    def test_run_logger_redacts_nested_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-nested-redact")
        with redirect_stdout(buffer):
            logger.event(
                "run.start",
                outcome="start",
                config={"api_token": "secret123", "workspace": "acme"},
            )
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual(REDACTED_VALUE, parsed["config"]["api_token"])
        self.assertEqual("acme", parsed["config"]["workspace"])
        self.assertNotIn("secret123", buffer.getvalue())

    def test_run_logger_redacts_sensitive_field_with_list_value(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-list-redact")
        with redirect_stdout(buffer):
            logger.event(
                "run.start",
                outcome="start",
                api_tokens=["token1", "token2", "token3"],
            )
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual(REDACTED_VALUE, parsed["api_tokens"])

    def test_run_logger_handles_none_values(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-none")
        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                provider="bitbucket",
                workspace=None,
                branch=None,
            )
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertNotIn("workspace", parsed)
        self.assertNotIn("branch", parsed)

    def test_run_logger_writes_to_file_when_log_file_provided(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="text", log_file=log_file, run_id="run-file-test")
            logger.event("test.event", outcome="success", provider="bitbucket")
            logger.close()

            with open(log_file, "r", encoding="utf-8") as handle:
                content = handle.read()

            self.assertIn("test.event", content)
            self.assertIn("outcome=success", content)
            self.assertIn("run_id=run-file-test", content)

    def test_run_logger_creates_log_directory_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "logs", "nested", "test.log")
            logger = RunLogger(log_format="json", log_file=log_file, run_id="run-nested")
            logger.event("test.event", outcome="success")
            logger.close()

            self.assertTrue(os.path.exists(log_file))

    def test_run_logger_flushes_after_each_event(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            logger = RunLogger(log_format="text", log_file=log_file, run_id="run-flush")
            logger.event("event.one", outcome="success")

            with open(log_file, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("event.one", content)

            logger.event("event.two", outcome="success")
            logger.close()

    def test_run_logger_appends_to_existing_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            with open(log_file, "w", encoding="utf-8") as handle:
                handle.write("existing line\n")

            logger = RunLogger(log_format="text", log_file=log_file, run_id="run-append")
            logger.event("new.event", outcome="success")
            logger.close()

            with open(log_file, "r", encoding="utf-8") as handle:
                lines = handle.readlines()

            self.assertEqual(2, len(lines))
            self.assertIn("existing line", lines[0])
            self.assertIn("new.event", lines[1])

    def test_run_logger_context_manager_closes_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = os.path.join(tmp_dir, "test.log")
            with RunLogger(log_format="text", log_file=log_file, run_id="run-ctx") as logger:
                logger.event("test.event", outcome="success")
                self.assertIsNotNone(logger._log_file_handle)

            self.assertIsNone(logger._log_file_handle)

    def test_run_logger_close_is_idempotent(self):
        logger = RunLogger(log_format="text", run_id="run-close")
        logger.close()
        logger.close()

    def test_run_logger_includes_message_when_provided(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-message")
        with redirect_stdout(buffer):
            logger.event(
                "auth.token.source",
                outcome="fallback",
                message="Token env variable not set, falling back to prompt",
            )
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual("Token env variable not set, falling back to prompt", parsed["message"])

    def test_run_logger_includes_error_field_in_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-error")
        with redirect_stdout(buffer):
            logger.event(
                "repository.finish",
                outcome="failed",
                level="ERROR",
                error="Failed cloning repository",
                provider="github",
            )
        output = buffer.getvalue().strip()
        logger.close()

        self.assertIn("[ERROR]", output)
        self.assertIn("error=Failed cloning repository", output)

    def test_run_logger_includes_duration_ms_in_text_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="text", run_id="run-duration")
        with redirect_stdout(buffer):
            logger.event(
                "sync.mirror.update",
                outcome="success",
                duration_ms=1500,
                provider="bitbucket",
            )
        output = buffer.getvalue().strip()
        logger.close()

        self.assertIn("duration_ms=1500", output)

    def test_run_logger_returns_event_record(self):
        logger = RunLogger(log_format="text", run_id="run-return")
        with redirect_stdout(io.StringIO()):
            record = logger.event("test.action", outcome="info", custom_field="value")
        logger.close()

        self.assertEqual("test.action", record["action"])
        self.assertEqual("info", record["outcome"])
        self.assertEqual("value", record["custom_field"])

    def test_null_logger_event_returns_empty_dict(self):
        logger = NullLogger()
        record = logger.event("test.action", outcome="info", provider="bitbucket")
        self.assertEqual({}, record)

    def test_null_logger_close_does_not_raise(self):
        logger = NullLogger()
        result = logger.close()
        self.assertIsNone(result)

    def test_null_logger_has_default_run_id(self):
        logger = NullLogger()
        self.assertEqual("run-null", logger.run_id)

    def test_null_logger_has_text_log_format(self):
        logger = NullLogger()
        self.assertEqual("text", logger.log_format)

    def test_sensitive_key_parts_coverage(self):
        self.assertIn("token", SENSITIVE_KEY_PARTS)
        self.assertIn("password", SENSITIVE_KEY_PARTS)
        self.assertIn("secret", SENSITIVE_KEY_PARTS)
        self.assertIn("ssh_key_path", SENSITIVE_KEY_PARTS)

    def test_run_logger_redacts_field_with_secret_in_key_name(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-secret")
        with redirect_stdout(buffer):
            logger.event("run.start", outcome="start", client_secret="secret-value")
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual(REDACTED_VALUE, parsed["client_secret"])
        self.assertNotIn("secret-value", buffer.getvalue())

    def test_run_logger_case_insensitive_sensitive_key_detection(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-case")
        with redirect_stdout(buffer):
            logger.event("run.start", outcome="start", API_TOKEN="case-secret", Password="pwd")
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual(REDACTED_VALUE, parsed["API_TOKEN"])
        self.assertEqual(REDACTED_VALUE, parsed["Password"])

    def test_run_logger_sanitizes_deeply_nested_dicts(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-deep")
        with redirect_stdout(buffer):
            logger.event(
                "run.start",
                outcome="start",
                config={
                    "auth": {"token": "secret", "user": "john"},
                    "workspace": "acme",
                },
            )
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        self.assertEqual(REDACTED_VALUE, parsed["config"]["auth"]["token"])
        self.assertEqual("john", parsed["config"]["auth"]["user"])
        self.assertEqual("acme", parsed["config"]["workspace"])

    def test_run_logger_timestamp_is_utc_iso_format(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-timestamp")
        with redirect_stdout(buffer):
            logger.event("test.event", outcome="info")
        parsed = json.loads(buffer.getvalue().strip())
        logger.close()

        timestamp_str = parsed["timestamp"]
        parsed_timestamp = datetime.fromisoformat(timestamp_str)
        self.assertEqual(timezone.utc, parsed_timestamp.tzinfo)

    def test_run_logger_json_output_is_sorted(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-sorted")
        with redirect_stdout(buffer):
            logger.event("test.event", outcome="info", zebra="last", alpha="first")
        output_line = buffer.getvalue().strip()
        logger.close()

        parsed = json.loads(output_line)
        keys = list(parsed.keys())
        sorted_keys = sorted(keys)
        self.assertEqual(sorted_keys, keys)


if __name__ == "__main__":
    unittest.main()