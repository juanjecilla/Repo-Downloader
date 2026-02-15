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
        error = RepoDownloaderError("Base error message")
        self.assertIsInstance(error, Exception)
        self.assertEqual("Base error message", str(error))

    def test_provider_configuration_error_inherits_from_base(self):
        error = ProviderConfigurationError("Invalid configuration")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertIsInstance(error, Exception)
        self.assertEqual("Invalid configuration", str(error))

    def test_provider_not_implemented_error_inherits_from_base(self):
        error = ProviderNotImplementedError("Provider not implemented")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("Provider not implemented", str(error))

    def test_authentication_error_inherits_from_base(self):
        error = AuthenticationError("Authentication failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("Authentication failed", str(error))

    def test_remote_api_error_inherits_from_base(self):
        error = RemoteAPIError("API request failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("API request failed", str(error))

    def test_repository_sync_error_inherits_from_base(self):
        error = RepositorySyncError("Sync operation failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("Sync operation failed", str(error))

    def test_run_lock_error_inherits_from_base(self):
        error = RunLockError("Lock acquisition failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("Lock acquisition failed", str(error))

    def test_errors_can_be_raised_and_caught_as_base_type(self):
        errors_to_test = [
            ProviderConfigurationError("test"),
            ProviderNotImplementedError("test"),
            AuthenticationError("test"),
            RemoteAPIError("test"),
            RepositorySyncError("test"),
            RunLockError("test"),
        ]

        for error in errors_to_test:
            with self.assertRaises(RepoDownloaderError):
                raise error

    def test_errors_can_be_caught_individually(self):
        with self.assertRaises(AuthenticationError):
            raise AuthenticationError("auth failed")

        with self.assertRaises(RemoteAPIError):
            raise RemoteAPIError("api failed")

        with self.assertRaises(RepositorySyncError):
            raise RepositorySyncError("sync failed")

    def test_errors_support_exception_chaining(self):
        try:
            try:
                raise ValueError("root cause")
            except ValueError as exc:
                raise RepositorySyncError("sync failed") from exc
        except RepositorySyncError as sync_error:
            self.assertIsNotNone(sync_error.__cause__)
            self.assertIsInstance(sync_error.__cause__, ValueError)
            self.assertEqual("root cause", str(sync_error.__cause__))

    def test_errors_preserve_exception_context(self):
        try:
            try:
                raise ValueError("original error")
            except ValueError:
                raise AuthenticationError("auth failed")
        except AuthenticationError as auth_error:
            self.assertIsNotNone(auth_error.__context__)
            self.assertIsInstance(auth_error.__context__, ValueError)

    def test_error_messages_can_contain_formatting(self):
        provider = "bitbucket"
        username = "testuser"
        error = AuthenticationError(
            f"Authentication failed for provider '{provider}' with username '{username}'"
        )
        self.assertIn("bitbucket", str(error))
        self.assertIn("testuser", str(error))

    def test_error_can_be_caught_by_multiple_except_clauses(self):
        caught_as_base = False
        caught_as_specific = False

        try:
            raise RemoteAPIError("api error")
        except RepoDownloaderError:
            caught_as_base = True

        try:
            raise RemoteAPIError("api error")
        except RemoteAPIError:
            caught_as_specific = True

        self.assertTrue(caught_as_base)
        self.assertTrue(caught_as_specific)


if __name__ == "__main__":
    unittest.main()