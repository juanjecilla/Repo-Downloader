import os
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from utils.log_utils import NullLogger, RunLogger


class TestRunLoggerFileOutput(unittest.TestCase):
    def test_event_writes_to_log_file(self):
        with tempfile.NamedTemporaryFile(mode="r", suffix=".log", delete=False) as tmp:
            path = tmp.name

        try:
            logger = RunLogger(log_file=path)
            logger.event("test.action", outcome="success")
            logger.close()

            with open(path, encoding="utf-8") as handle:
                content = handle.read()

            self.assertIn("test.action", content)
            self.assertIn("success", content)
        finally:
            os.unlink(path)

    def test_event_writes_to_log_file_in_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "sub", "run.log")
            logger = RunLogger(log_file=log_path)
            logger.event("action", outcome="ok")
            logger.close()

            self.assertTrue(os.path.isfile(log_path))
            with open(log_path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("action", content)

    def test_close_is_idempotent(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
            path = tmp.name
        try:
            logger = RunLogger(log_file=path)
            logger.close()
            logger.close()  # second close must not raise
        finally:
            os.unlink(path)


class TestRunLoggerContextManager(unittest.TestCase):
    def test_context_manager_enter_returns_self(self):
        logger = RunLogger()
        with logger as ctx:
            self.assertIs(ctx, logger)

    def test_context_manager_exit_closes_file(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
            path = tmp.name
        try:
            with RunLogger(log_file=path) as logger:
                logger.event("inside", outcome="ok")
            self.assertIsNone(logger._log_file_handle)  # noqa: SLF001  # pylint: disable=protected-access
        finally:
            os.unlink(path)


class TestRunLoggerEventRendering(unittest.TestCase):
    def test_event_with_message_included_in_text_output(self):
        logger = RunLogger(log_format="text")
        captured = StringIO()
        with patch("builtins.print", lambda line: captured.write(line + "\n")):
            record = logger.event("task.run", outcome="success", message="all done")

        self.assertIn("all done", captured.getvalue())
        self.assertEqual("all done", record["message"])

    def test_event_with_message_in_json_format(self):
        import json

        logger = RunLogger(log_format="json")
        captured = StringIO()
        with patch("builtins.print", lambda line: captured.write(line + "\n")):
            logger.event("json.event", outcome="ok", message="hello")

        line = captured.getvalue().strip()
        payload = json.loads(line)
        self.assertEqual("hello", payload["message"])
        self.assertEqual("json.event", payload["action"])

    def test_event_without_message_excludes_field(self):
        logger = RunLogger(log_format="text")
        captured = StringIO()
        with patch("builtins.print", lambda line: captured.write(line + "\n")):
            record = logger.event("no.msg", outcome="ok")

        self.assertNotIn("message", record)


class TestRunLoggerSanitization(unittest.TestCase):
    def test_list_value_sanitized_per_item(self):
        logger = RunLogger()
        result = logger._sanitize_value("values", ["a", "b"])  # noqa: SLF001  # pylint: disable=protected-access
        self.assertEqual(["a", "b"], result)

    def test_list_containing_dict_with_sensitive_key_is_redacted(self):
        logger = RunLogger()
        result = logger._sanitize_value("data", [{"token": "secret"}])  # noqa: SLF001  # pylint: disable=protected-access
        self.assertEqual([{"token": "***REDACTED***"}], result)


class TestNullLogger(unittest.TestCase):
    def test_event_returns_empty_dict(self):
        logger = NullLogger()
        result = logger.event("anything", outcome="ok", foo="bar")
        self.assertEqual({}, result)

    def test_close_returns_none(self):
        logger = NullLogger()
        self.assertIsNone(logger.close())

    def test_log_format_is_text(self):
        self.assertEqual("text", NullLogger.log_format)

    def test_run_id_is_run_null(self):
        self.assertEqual("run-null", NullLogger.run_id)


if __name__ == "__main__":
    unittest.main()
