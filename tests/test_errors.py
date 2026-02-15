import unittest

from utils.errors import (
    AuthenticationError,
    ProviderConfigurationError,
    ProviderNotImplementedError,
    RemoteAPIError,
    RepoDownloaderError,
    RepositorySyncError,
    RunLockError,
)


class TestErrors(unittest.TestCase):
    def test_repo_downloader_error_is_base_exception(self):
        error = RepoDownloaderError("base error")
        self.assertIsInstance(error, Exception)
        self.assertEqual("base error", str(error))

    def test_provider_configuration_error_inherits_from_base(self):
        error = ProviderConfigurationError("config error")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertIsInstance(error, Exception)

    def test_provider_not_implemented_error_inherits_from_base(self):
        error = ProviderNotImplementedError("not implemented")
        self.assertIsInstance(error, RepoDownloaderError)

    def test_authentication_error_inherits_from_base(self):
        error = AuthenticationError("auth failed")
        self.assertIsInstance(error, RepoDownloaderError)

    def test_remote_api_error_inherits_from_base(self):
        error = RemoteAPIError("api error")
        self.assertIsInstance(error, RepoDownloaderError)

    def test_repository_sync_error_inherits_from_base(self):
        error = RepositorySyncError("sync error")
        self.assertIsInstance(error, RepoDownloaderError)

    def test_run_lock_error_inherits_from_base(self):
        error = RunLockError("lock error")
        self.assertIsInstance(error, RepoDownloaderError)

    def test_errors_can_be_raised_and_caught(self):
        with self.assertRaises(AuthenticationError) as ctx:
            raise AuthenticationError("test auth error")
        self.assertEqual("test auth error", str(ctx.exception))

    def test_errors_can_be_caught_as_base_exception(self):
        with self.assertRaises(RepoDownloaderError):
            raise RepositorySyncError("sync failed")

    def test_errors_preserve_error_messages(self):
        message = "Detailed error message with context"
        error = RemoteAPIError(message)
        self.assertEqual(message, str(error))

    def test_errors_support_chained_exceptions(self):
        original = ValueError("original error")
        try:
            raise AuthenticationError("auth failed") from original
        except AuthenticationError as exc:
            self.assertIs(original, exc.__cause__)

    def test_provider_configuration_error_for_missing_username(self):
        error = ProviderConfigurationError("Argument '--username' is required for provider 'bitbucket'.")
        self.assertIn("username", str(error))
        self.assertIn("bitbucket", str(error))

    def test_authentication_error_for_token_failure(self):
        error = AuthenticationError("Authentication failed for 'https://api.example.com/user' (status 401)")
        self.assertIn("401", str(error))
        self.assertIn("Authentication failed", str(error))

    def test_remote_api_error_for_http_failure(self):
        error = RemoteAPIError("Request to 'https://api.example.com/repos' failed with status 500")
        self.assertIn("500", str(error))

    def test_repository_sync_error_for_clone_failure(self):
        error = RepositorySyncError("Failed cloning repository from git@example.com:acme/repo.git: error message")
        self.assertIn("Failed cloning", str(error))
        self.assertIn("git@example.com:acme/repo.git", str(error))

    def test_repository_sync_error_for_checkout_failure(self):
        error = RepositorySyncError("Failed checking out branch 'feature/x': error message")
        self.assertIn("checking out", str(error))
        self.assertIn("feature/x", str(error))

    def test_run_lock_error_for_active_lock(self):
        error = RunLockError(
            "Another backup run is active for this output root (provider=bitbucket, pid=12345, run_id=run-abc). "
            "Use --force-lock to replace the existing lock."
        )
        self.assertIn("active", str(error))
        self.assertIn("--force-lock", str(error))
        self.assertIn("pid=12345", str(error))

    def test_provider_not_implemented_error_message(self):
        error = ProviderNotImplementedError("Provider 'gitlab' is not implemented yet.")
        self.assertIn("not implemented", str(error))
        self.assertIn("gitlab", str(error))


if __name__ == "__main__":
    unittest.main()