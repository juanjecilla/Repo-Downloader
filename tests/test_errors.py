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
        self.assertTrue(issubclass(RepoDownloaderError, Exception))

    def test_provider_configuration_error_inherits_from_base(self):
        self.assertTrue(issubclass(ProviderConfigurationError, RepoDownloaderError))

    def test_provider_not_implemented_error_inherits_from_base(self):
        self.assertTrue(issubclass(ProviderNotImplementedError, RepoDownloaderError))

    def test_authentication_error_inherits_from_base(self):
        self.assertTrue(issubclass(AuthenticationError, RepoDownloaderError))

    def test_remote_api_error_inherits_from_base(self):
        self.assertTrue(issubclass(RemoteAPIError, RepoDownloaderError))

    def test_repository_sync_error_inherits_from_base(self):
        self.assertTrue(issubclass(RepositorySyncError, RepoDownloaderError))

    def test_run_lock_error_inherits_from_base(self):
        self.assertTrue(issubclass(RunLockError, RepoDownloaderError))

    def test_exceptions_can_be_raised_and_caught_as_base_class(self):
        exceptions = [
            ProviderConfigurationError("config error"),
            ProviderNotImplementedError("not implemented error"),
            AuthenticationError("auth error"),
            RemoteAPIError("api error"),
            RepositorySyncError("sync error"),
            RunLockError("lock error"),
        ]

        for exc in exceptions:
            with self.subTest(exception=type(exc).__name__):
                try:
                    raise exc
                except RepoDownloaderError as caught:
                    self.assertIsInstance(caught, RepoDownloaderError)
                    self.assertTrue(len(str(caught)) > 0)

    def test_exceptions_preserve_error_messages(self):
        test_cases = [
            (ProviderConfigurationError, "Missing configuration"),
            (ProviderNotImplementedError, "Provider not available"),
            (AuthenticationError, "Invalid credentials"),
            (RemoteAPIError, "API request failed"),
            (RepositorySyncError, "Git operation failed"),
            (RunLockError, "Lock acquisition failed"),
        ]

        for exc_class, message in test_cases:
            with self.subTest(exception=exc_class.__name__):
                exc = exc_class(message)
                self.assertEqual(message, str(exc))

    def test_exceptions_can_be_caught_by_specific_type(self):
        try:
            raise AuthenticationError("test auth error")
        except AuthenticationError as exc:
            self.assertIsInstance(exc, AuthenticationError)
            self.assertEqual("test auth error", str(exc))

    def test_base_exception_can_be_instantiated_directly(self):
        exc = RepoDownloaderError("base error message")
        self.assertEqual("base error message", str(exc))

    def test_exceptions_support_exception_chaining(self):
        original = ValueError("original error")
        try:
            try:
                raise original
            except ValueError as exc:
                raise RepositorySyncError("sync failed") from exc
        except RepositorySyncError as caught:
            self.assertIsNotNone(caught.__cause__)
            self.assertIsInstance(caught.__cause__, ValueError)
            self.assertEqual("original error", str(caught.__cause__))


if __name__ == "__main__":
    unittest.main()