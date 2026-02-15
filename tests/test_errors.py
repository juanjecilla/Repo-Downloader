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


class TestErrorHierarchy(unittest.TestCase):
    def test_repo_downloader_error_is_base_exception(self):
        error = RepoDownloaderError("base error")
        self.assertIsInstance(error, Exception)
        self.assertEqual("base error", str(error))

    def test_provider_configuration_error_inherits_from_base(self):
        error = ProviderConfigurationError("config error")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("config error", str(error))

    def test_provider_not_implemented_error_inherits_from_base(self):
        error = ProviderNotImplementedError("not implemented")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("not implemented", str(error))

    def test_authentication_error_inherits_from_base(self):
        error = AuthenticationError("auth failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("auth failed", str(error))

    def test_remote_api_error_inherits_from_base(self):
        error = RemoteAPIError("api error")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("api error", str(error))

    def test_repository_sync_error_inherits_from_base(self):
        error = RepositorySyncError("sync failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("sync failed", str(error))

    def test_run_lock_error_inherits_from_base(self):
        error = RunLockError("lock error")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("lock error", str(error))

    def test_errors_can_be_caught_by_base_class(self):
        errors = [
            ProviderConfigurationError("config"),
            ProviderNotImplementedError("not impl"),
            AuthenticationError("auth"),
            RemoteAPIError("api"),
            RepositorySyncError("sync"),
            RunLockError("lock"),
        ]
        for error in errors:
            try:
                raise error
            except RepoDownloaderError as caught:
                self.assertIsInstance(caught, RepoDownloaderError)

    def test_errors_preserve_traceback_with_chaining(self):
        try:
            try:
                raise ValueError("original error")
            except ValueError as exc:
                raise RepositorySyncError("wrapped error") from exc
        except RepositorySyncError as sync_error:
            self.assertIsNotNone(sync_error.__cause__)
            self.assertIsInstance(sync_error.__cause__, ValueError)
            self.assertEqual("original error", str(sync_error.__cause__))


class TestErrorMessages(unittest.TestCase):
    def test_authentication_error_message_formatting(self):
        error = AuthenticationError("Authentication failed for 'https://api.example.com/user'")
        self.assertIn("Authentication failed", str(error))
        self.assertIn("https://api.example.com/user", str(error))

    def test_repository_sync_error_message_formatting(self):
        error = RepositorySyncError("Failed cloning repository from git@example.com:repo.git")
        self.assertIn("Failed cloning", str(error))
        self.assertIn("git@example.com:repo.git", str(error))

    def test_run_lock_error_message_formatting(self):
        error = RunLockError(
            "Run lock is held by another process (PID 12345). "
            "Use --force-lock to override."
        )
        self.assertIn("PID 12345", str(error))
        self.assertIn("--force-lock", str(error))


class TestErrorUsagePatterns(unittest.TestCase):
    def test_catching_specific_error_type(self):
        caught = False
        try:
            raise AuthenticationError("test auth error")
        except AuthenticationError:
            caught = True
        self.assertTrue(caught)

    def test_catching_multiple_error_types(self):
        for error_class in (AuthenticationError, RemoteAPIError, RepositorySyncError):
            caught = False
            try:
                raise error_class("test error")
            except (AuthenticationError, RemoteAPIError, RepositorySyncError):
                caught = True
            self.assertTrue(caught)

    def test_error_can_be_re_raised(self):
        with self.assertRaises(RepositorySyncError) as context:
            try:
                raise RepositorySyncError("original")
            except RepositorySyncError:
                raise
        self.assertEqual("original", str(context.exception))


if __name__ == "__main__":
    unittest.main()