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
