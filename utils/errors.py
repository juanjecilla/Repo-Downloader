import re


REDACTED_TEXT = "***REDACTED***"
_REDACTION_PATTERNS = (
    re.compile(r"(?i)(token|password|secret)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)"),
)


def redact_sensitive_text(text, sensitive_values=None):
    rendered = str(text)
    redacted = rendered
    for value in sensitive_values or []:
        if value:
            redacted = redacted.replace(str(value), REDACTED_TEXT)
    for pattern in _REDACTION_PATTERNS:
        redacted = pattern.sub(rf"\1{REDACTED_TEXT}", redacted)
    return redacted


class RepoDownloaderError(Exception):
    """Base exception for repo downloader failures."""


class ProviderConfigurationError(RepoDownloaderError):
    """Raised when provider inputs are missing or invalid."""


class ProviderNotImplementedError(RepoDownloaderError):
    """Raised when a provider exists as a stub only."""


class AuthenticationError(RepoDownloaderError):
    """Raised when provider authentication fails."""


class RemoteAPIError(RepoDownloaderError):
    """Raised for provider API failures."""


class RepositorySyncError(RepoDownloaderError):
    """Raised for clone/fetch/checkout failures."""


class RunLockError(RepoDownloaderError):
    """Raised when a backup run lock cannot be acquired."""
