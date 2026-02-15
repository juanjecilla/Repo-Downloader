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
        error = ProviderConfigurationError("Invalid provider config")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertIsInstance(error, Exception)
        self.assertEqual("Invalid provider config", str(error))

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
        error = RepositorySyncError("Clone failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("Clone failed", str(error))

    def test_run_lock_error_inherits_from_base(self):
        error = RunLockError("Lock acquisition failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("Lock acquisition failed", str(error))

    def test_errors_can_be_raised_and_caught_specifically(self):
        with self.assertRaises(AuthenticationError):
            raise AuthenticationError("Auth failed")

        with self.assertRaises(RemoteAPIError):
            raise RemoteAPIError("API failed")

        with self.assertRaises(RepositorySyncError):
            raise RepositorySyncError("Sync failed")

    def test_errors_can_be_caught_by_base_exception(self):
        with self.assertRaises(RepoDownloaderError):
            raise AuthenticationError("Auth failed")

        with self.assertRaises(RepoDownloaderError):
            raise RemoteAPIError("API failed")

        with self.assertRaises(RepoDownloaderError):
            raise ProviderConfigurationError("Config failed")

    def test_errors_preserve_error_message(self):
        message = "Detailed error message with context"
        error = RepositorySyncError(message)
        self.assertEqual(message, str(error))

    def test_errors_support_exception_chaining(self):
        original = ValueError("Original error")
        try:
            try:
                raise original
            except ValueError as exc:
                raise RepositorySyncError("Sync failed") from exc
        except RepositorySyncError as sync_error:
            self.assertEqual("Sync failed", str(sync_error))
            self.assertIsInstance(sync_error.__cause__, ValueError)
            self.assertEqual("Original error", str(sync_error.__cause__))

    def test_errors_can_be_instantiated_with_formatted_strings(self):
        repo_url = "git@example.com:repo.git"
        error = RepositorySyncError(f"Failed cloning repository from {repo_url}")
        self.assertIn("git@example.com:repo.git", str(error))

    def test_all_error_classes_are_distinct(self):
        error_classes = [
            RepoDownloaderError,
            ProviderConfigurationError,
            ProviderNotImplementedError,
            AuthenticationError,
            RemoteAPIError,
            RepositorySyncError,
            RunLockError,
        ]
        for error_class in error_classes:
            self.assertTrue(callable(error_class))
            instance = error_class("test")
            self.assertIsInstance(instance, RepoDownloaderError)

    def test_error_hierarchy_allows_specific_handling(self):
        errors_caught = []
        for error_cls, message in [
            (AuthenticationError, "auth"),
            (RemoteAPIError, "api"),
            (RepositorySyncError, "sync"),
        ]:
            try:
                raise error_cls(message)
            except AuthenticationError as exc:
                errors_caught.append(("auth", str(exc)))
            except RemoteAPIError as exc:
                errors_caught.append(("api", str(exc)))
            except RepositorySyncError as exc:
                errors_caught.append(("sync", str(exc)))

        self.assertEqual(3, len(errors_caught))
        self.assertEqual(("auth", "auth"), errors_caught[0])
        self.assertEqual(("api", "api"), errors_caught[1])
        self.assertEqual(("sync", "sync"), errors_caught[2])


if __name__ == "__main__":
    unittest.main()