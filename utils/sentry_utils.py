"""Sentry helpers for optional CLI error monitoring."""

import os

from utils.errors import redact_sensitive_text

_SENTRY_STATE = {"enabled": False}


def resolve_sentry_settings(args=None):
    args = args or object()
    dsn = getattr(args, "sentry_dsn", None) or os.environ.get("REPO_DOWNLOADER_SENTRY_DSN")
    environment = (
        getattr(args, "sentry_environment", None)
        or os.environ.get("REPO_DOWNLOADER_SENTRY_ENVIRONMENT")
    )
    release = (
        getattr(args, "sentry_release", None)
        or os.environ.get("REPO_DOWNLOADER_SENTRY_RELEASE")
    )
    return {
        "dsn": dsn,
        "environment": environment,
        "release": release,
    }


def _before_send(event, _hint):
    message = event.get("message")
    if isinstance(message, str):
        event["message"] = redact_sensitive_text(message)

    exception_payload = event.get("exception", {})
    values = exception_payload.get("values", []) if isinstance(exception_payload, dict) else []
    for value in values:
        if not isinstance(value, dict):
            continue
        error_value = value.get("value")
        if isinstance(error_value, str):
            value["value"] = redact_sensitive_text(error_value)
    return event


def initialize_sentry(args=None, logger=None):
    settings = resolve_sentry_settings(args=args)
    dsn = settings["dsn"]

    if not dsn:
        _SENTRY_STATE["enabled"] = False
        if logger:
            logger.event("sentry.init", outcome="skipped", source="disabled")
        return {"enabled": False, **settings}

    try:
        import sentry_sdk
    except ModuleNotFoundError:
        _SENTRY_STATE["enabled"] = False
        if logger:
            logger.event(
                "sentry.init",
                outcome="failed",
                level="WARNING",
                source="missing_dependency",
            )
        return {"enabled": False, **settings}

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=settings["environment"],
            release=settings["release"],
            traces_sample_rate=0.0,
            before_send=_before_send,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _SENTRY_STATE["enabled"] = False
        if logger:
            logger.event(
                "sentry.init",
                outcome="failure",
                level="WARNING",
                source="init_error",
                message=str(exc),
            )
        return {"enabled": False, **settings}
    _SENTRY_STATE["enabled"] = True
    if logger:
        logger.event("sentry.init", outcome="success", source="environment")
    return {"enabled": True, **settings}


def set_sentry_tags(command=None, provider=None, mode=None, run_id=None):
    if not _SENTRY_STATE["enabled"]:
        return
    try:
        import sentry_sdk
    except ModuleNotFoundError:
        return

    tags = {
        "command": command,
        "provider": provider,
        "mode": mode,
        "run_id": run_id,
    }
    for key, value in tags.items():
        if value is not None:
            sentry_sdk.set_tag(key, value)


def capture_exception(exc):
    if not _SENTRY_STATE["enabled"]:
        return
    try:
        import sentry_sdk
    except ModuleNotFoundError:
        return
    sentry_sdk.capture_exception(exc)
