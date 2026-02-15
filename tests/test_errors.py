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
        exc = RepoDownloaderError("base error")
        self.assertIsInstance(exc, Exception)
        self.assertEqual("base error", str(exc))

    def test_provider_configuration_error_inherits_from_base(self):
        exc = ProviderConfigurationError("config error")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertIsInstance(exc, Exception)
        self.assertEqual("config error", str(exc))

    def test_provider_not_implemented_error_inherits_from_base(self):
        exc = ProviderNotImplementedError("not implemented")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertEqual("not implemented", str(exc))

    def test_authentication_error_inherits_from_base(self):
        exc = AuthenticationError("auth failed")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertEqual("auth failed", str(exc))

    def test_remote_api_error_inherits_from_base(self):
        exc = RemoteAPIError("api error")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertEqual("api error", str(exc))

    def test_repository_sync_error_inherits_from_base(self):
        exc = RepositorySyncError("sync error")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertEqual("sync error", str(exc))

    def test_run_lock_error_inherits_from_base(self):
        exc = RunLockError("lock error")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertEqual("lock error", str(exc))

    def test_exceptions_can_be_caught_by_base_class(self):
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

    def test_exceptions_preserve_traceback_with_from_clause(self):
        original = ValueError("original error")
        try:
            try:
                raise original
            except ValueError as exc:
                raise AuthenticationError("wrapped error") from exc
        except AuthenticationError as caught:
            self.assertIsNotNone(caught.__cause__)
            self.assertIs(caught.__cause__, original)

    def test_error_messages_are_descriptive(self):
        exc = RepositorySyncError("Failed cloning repository from git@example.com:repo.git")
        self.assertIn("Failed cloning", str(exc))
        self.assertIn("git@example.com:repo.git", str(exc))


if __name__ == "__main__":
    unittest.main()