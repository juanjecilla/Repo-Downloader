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
    def test_base_error_is_exception(self):
        self.assertTrue(issubclass(RepoDownloaderError, Exception))

    def test_base_error_can_be_raised_with_message(self):
        message = "Test error message"
        with self.assertRaises(RepoDownloaderError) as context:
            raise RepoDownloaderError(message)
        self.assertEqual(message, str(context.exception))

    def test_provider_configuration_error_inherits_base(self):
        self.assertTrue(issubclass(ProviderConfigurationError, RepoDownloaderError))

    def test_provider_not_implemented_error_inherits_base(self):
        self.assertTrue(issubclass(ProviderNotImplementedError, RepoDownloaderError))

    def test_authentication_error_inherits_base(self):
        self.assertTrue(issubclass(AuthenticationError, RepoDownloaderError))

    def test_remote_api_error_inherits_base(self):
        self.assertTrue(issubclass(RemoteAPIError, RepoDownloaderError))

    def test_repository_sync_error_inherits_base(self):
        self.assertTrue(issubclass(RepositorySyncError, RepoDownloaderError))

    def test_run_lock_error_inherits_base(self):
        self.assertTrue(issubclass(RunLockError, RepoDownloaderError))

    def test_all_errors_can_be_caught_as_base_exception(self):
        error_classes = [
            ProviderConfigurationError,
            ProviderNotImplementedError,
            AuthenticationError,
            RemoteAPIError,
            RepositorySyncError,
            RunLockError,
        ]

        for error_class in error_classes:
            with self.subTest(error_class=error_class.__name__):
                try:
                    raise error_class("test message")
                except RepoDownloaderError as exc:
                    self.assertIsInstance(exc, error_class)
                    self.assertEqual("test message", str(exc))

    def test_provider_configuration_error_message(self):
        message = "Provider 'unknown' is not configured"
        with self.assertRaises(ProviderConfigurationError) as context:
            raise ProviderConfigurationError(message)
        self.assertIn("unknown", str(context.exception))

    def test_provider_not_implemented_error_message(self):
        message = "Provider 'gitlab' is not implemented yet"
        with self.assertRaises(ProviderNotImplementedError) as context:
            raise ProviderNotImplementedError(message)
        self.assertIn("gitlab", str(context.exception))

    def test_authentication_error_message(self):
        message = "Authentication failed for 'api.example.com' (status 401)"
        with self.assertRaises(AuthenticationError) as context:
            raise AuthenticationError(message)
        self.assertIn("401", str(context.exception))

    def test_remote_api_error_message(self):
        message = "Request to 'https://api.example.com/repos' failed with status 500"
        with self.assertRaises(RemoteAPIError) as context:
            raise RemoteAPIError(message)
        self.assertIn("500", str(context.exception))

    def test_repository_sync_error_message(self):
        message = "Failed cloning repository from git@example.com:repo.git"
        with self.assertRaises(RepositorySyncError) as context:
            raise RepositorySyncError(message)
        self.assertIn("cloning", str(context.exception))

    def test_run_lock_error_message(self):
        message = "Another backup run is active (pid=12345)"
        with self.assertRaises(RunLockError) as context:
            raise RunLockError(message)
        self.assertIn("12345", str(context.exception))

    def test_errors_can_be_chained_with_cause(self):
        original_error = ValueError("Original error")
        message = "Failed due to original error"

        with self.assertRaises(RepositorySyncError) as context:
            try:
                raise original_error
            except ValueError as exc:
                raise RepositorySyncError(message) from exc

        self.assertIsInstance(context.exception.__cause__, ValueError)
        self.assertEqual("Original error", str(context.exception.__cause__))

    def test_error_can_be_caught_by_specific_type(self):
        try:
            raise AuthenticationError("Auth failed")
        except AuthenticationError as exc:
            self.assertEqual("Auth failed", str(exc))
        except RepoDownloaderError:
            self.fail("Should have caught AuthenticationError specifically")

    def test_multiple_error_types_can_be_caught_together(self):
        caught_count = 0
        error_types = [AuthenticationError, RemoteAPIError, RepositorySyncError]

        for error_type in error_types:
            try:
                raise error_type("test")
            except (AuthenticationError, RemoteAPIError, RepositorySyncError):
                caught_count += 1

        self.assertEqual(3, caught_count)


if __name__ == "__main__":
    unittest.main()