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
    def test_all_errors_inherit_from_base_exception(self):
        error_classes = [
            ProviderConfigurationError,
            ProviderNotImplementedError,
            AuthenticationError,
            RemoteAPIError,
            RepositorySyncError,
            RunLockError,
        ]
        for error_class in error_classes:
            self.assertTrue(issubclass(error_class, RepoDownloaderError))

    def test_base_exception_is_exception_subclass(self):
        self.assertTrue(issubclass(RepoDownloaderError, Exception))

    def test_provider_configuration_error_message(self):
        error = ProviderConfigurationError("Missing username")
        self.assertEqual("Missing username", str(error))
        with self.assertRaises(ProviderConfigurationError) as context:
            raise error
        self.assertEqual("Missing username", str(context.exception))

    def test_provider_not_implemented_error_message(self):
        error = ProviderNotImplementedError("Provider 'gitlab' is not implemented yet.")
        self.assertIn("gitlab", str(error))
        with self.assertRaises(ProviderNotImplementedError):
            raise error

    def test_authentication_error_message(self):
        error = AuthenticationError("Invalid token")
        self.assertEqual("Invalid token", str(error))
        with self.assertRaises(AuthenticationError):
            raise error

    def test_remote_api_error_message(self):
        error = RemoteAPIError("Request failed with status 500")
        self.assertIn("500", str(error))
        with self.assertRaises(RemoteAPIError):
            raise error

    def test_repository_sync_error_message(self):
        error = RepositorySyncError("Failed cloning repository")
        self.assertIn("cloning", str(error))
        with self.assertRaises(RepositorySyncError):
            raise error

    def test_run_lock_error_message(self):
        error = RunLockError("Lock file already exists")
        self.assertIn("Lock file", str(error))
        with self.assertRaises(RunLockError):
            raise error

    def test_errors_can_be_caught_as_base_exception(self):
        error_classes = [
            AuthenticationError("auth error"),
            RemoteAPIError("api error"),
            RepositorySyncError("sync error"),
        ]
        for error in error_classes:
            with self.assertRaises(RepoDownloaderError):
                raise error

    def test_errors_preserve_cause_with_from_clause(self):
        original_error = ValueError("original")
        try:
            try:
                raise original_error
            except ValueError as exc:
                raise RemoteAPIError("wrapped error") from exc
        except RemoteAPIError as wrapped:
            self.assertEqual("wrapped error", str(wrapped))
            self.assertIsInstance(wrapped.__cause__, ValueError)
            self.assertEqual("original", str(wrapped.__cause__))


if __name__ == "__main__":
    unittest.main()