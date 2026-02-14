import json
import os
from datetime import datetime, timezone
from uuid import uuid4


REDACTED_VALUE = "***REDACTED***"
SENSITIVE_KEY_PARTS = ("token", "password", "secret", "ssh_key_path")


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class RunLogger:
    def __init__(self, log_format="text", log_file=None, run_id=None):
        self.log_format = log_format
        self.run_id = run_id or f"run-{uuid4().hex[:12]}"
        self._log_file_handle = None
        self._log_file_path = os.path.expanduser(log_file) if log_file else None

        if self._log_file_path:
            log_directory = os.path.dirname(self._log_file_path)
            if log_directory:
                os.makedirs(log_directory, exist_ok=True)
            self._log_file_handle = open(self._log_file_path, "a", encoding="utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        if self._log_file_handle:
            self._log_file_handle.close()
            self._log_file_handle = None

    def _is_sensitive_key(self, key_name):
        normalized = key_name.lower()
        return any(part in normalized for part in SENSITIVE_KEY_PARTS)

    def _sanitize_value(self, key_name, value):
        if self._is_sensitive_key(key_name):
            return REDACTED_VALUE

        if isinstance(value, dict):
            sanitized = {}
            for nested_key, nested_value in value.items():
                sanitized[nested_key] = self._sanitize_value(nested_key, nested_value)
            return sanitized
        if isinstance(value, list):
            sanitized_list = []
            for item in value:
                sanitized_list.append(self._sanitize_value(key_name, item))
            return sanitized_list
        return value

    def _sanitize_fields(self, fields):
        sanitized = {}
        for key, value in fields.items():
            if value is not None:
                sanitized[key] = self._sanitize_value(key, value)
        return sanitized

    def _render_text_line(self, record):
        parts = [
            f"[{record['level']}]",
            record["action"],
            f"outcome={record['outcome']}",
            f"run_id={record['run_id']}",
        ]

        for key in ("provider", "repository", "mode", "duration_ms", "error"):
            if key in record:
                parts.append(f"{key}={record[key]}")

        if "message" in record:
            parts.append(f"- {record['message']}")

        return " ".join(str(part) for part in parts)

    def event(self, action, outcome="info", level="INFO", message=None, **fields):
        record = {
            "timestamp": utc_now_iso(),
            "run_id": self.run_id,
            "level": level,
            "action": action,
            "outcome": outcome,
        }
        if message is not None:
            record["message"] = message
        record.update(self._sanitize_fields(fields))

        if self.log_format == "json":
            rendered = json.dumps(record, sort_keys=True)
        else:
            rendered = self._render_text_line(record)

        print(rendered)

        if self._log_file_handle:
            self._log_file_handle.write(rendered + "\n")
            self._log_file_handle.flush()

        return record


class NullLogger:
    log_format = "text"
    run_id = "run-null"

    def event(self, *_args, **_kwargs):
        return {}

    def close(self):
        return None
