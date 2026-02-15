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


class TestExceptionHierarchy(unittest.TestCase):
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


class TestRepoDownloaderError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(RepoDownloaderError) as context:
            raise RepoDownloaderError("Test error message")
        self.assertEqual("Test error message", str(context.exception))

    def test_can_be_caught_as_exception(self):
        try:
            raise RepoDownloaderError("Test error")
        except Exception as exc:
            self.assertIsInstance(exc, RepoDownloaderError)


class TestProviderConfigurationError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(ProviderConfigurationError) as context:
            raise ProviderConfigurationError("Invalid provider configuration")
        self.assertEqual("Invalid provider configuration", str(context.exception))

    def test_can_be_caught_as_repo_downloader_error(self):
        try:
            raise ProviderConfigurationError("Invalid configuration")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, ProviderConfigurationError)

    def test_can_be_caught_as_specific_exception(self):
        try:
            raise ProviderConfigurationError("Missing username")
        except ProviderConfigurationError as exc:
            self.assertEqual("Missing username", str(exc))


class TestProviderNotImplementedError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(ProviderNotImplementedError) as context:
            raise ProviderNotImplementedError("Provider 'gitlab' is not implemented yet")
        self.assertIn("not implemented", str(context.exception))

    def test_can_be_caught_as_repo_downloader_error(self):
        try:
            raise ProviderNotImplementedError("Not implemented")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, ProviderNotImplementedError)


class TestAuthenticationError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(AuthenticationError) as context:
            raise AuthenticationError("Authentication failed for 'https://api.example.com'")
        self.assertIn("Authentication failed", str(context.exception))

    def test_can_be_caught_as_repo_downloader_error(self):
        try:
            raise AuthenticationError("Invalid token")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, AuthenticationError)

    def test_supports_chained_exceptions(self):
        original = ValueError("Invalid credentials")
        try:
            raise AuthenticationError("Auth failed") from original
        except AuthenticationError as exc:
            self.assertIsNotNone(exc.__cause__)
            self.assertIsInstance(exc.__cause__, ValueError)


class TestRemoteAPIError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(RemoteAPIError) as context:
            raise RemoteAPIError("Request to 'https://api.example.com' failed")
        self.assertIn("Request to", str(context.exception))

    def test_can_be_caught_as_repo_downloader_error(self):
        try:
            raise RemoteAPIError("API error")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, RemoteAPIError)

    def test_supports_chained_exceptions(self):
        original = ConnectionError("Network timeout")
        try:
            raise RemoteAPIError("API request failed") from original
        except RemoteAPIError as exc:
            self.assertIsNotNone(exc.__cause__)
            self.assertIsInstance(exc.__cause__, ConnectionError)


class TestRepositorySyncError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(RepositorySyncError) as context:
            raise RepositorySyncError("Failed cloning repository from git@example.com:repo.git")
        self.assertIn("Failed cloning", str(context.exception))

    def test_can_be_caught_as_repo_downloader_error(self):
        try:
            raise RepositorySyncError("Sync failed")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, RepositorySyncError)

    def test_supports_chained_exceptions(self):
        try:
            from git.exc import GitCommandError
            original = GitCommandError("git", 128, stderr="fatal error")
            try:
                raise RepositorySyncError("Failed fetching repository") from original
            except RepositorySyncError as exc:
                self.assertIsNotNone(exc.__cause__)
                self.assertIsInstance(exc.__cause__, GitCommandError)
        except ImportError:
            self.skipTest("GitPython not available")


class TestRunLockError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(RunLockError) as context:
            raise RunLockError("Another backup run is active")
        self.assertIn("backup run", str(context.exception))

    def test_can_be_caught_as_repo_downloader_error(self):
        try:
            raise RunLockError("Lock error")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, RunLockError)

    def test_supports_chained_exceptions(self):
        original = OSError("Permission denied")
        try:
            raise RunLockError("Unable to acquire lock") from original
        except RunLockError as exc:
            self.assertIsNotNone(exc.__cause__)
            self.assertIsInstance(exc.__cause__, OSError)


class TestExceptionUsagePatterns(unittest.TestCase):
    def test_catch_all_downloader_errors(self):
        exceptions_to_test = [
            ProviderConfigurationError("config"),
            ProviderNotImplementedError("not impl"),
            AuthenticationError("auth"),
            RemoteAPIError("api"),
            RepositorySyncError("sync"),
            RunLockError("lock"),
        ]

        for exc in exceptions_to_test:
            with self.subTest(exception=exc.__class__.__name__):
                try:
                    raise exc
                except RepoDownloaderError as caught:
                    self.assertIsInstance(caught, RepoDownloaderError)

    def test_specific_exception_handling_order(self):
        caught_type = None
        try:
            raise AuthenticationError("Auth failed")
        except AuthenticationError:
            caught_type = "AuthenticationError"
        except RepoDownloaderError:
            caught_type = "RepoDownloaderError"
        except Exception:
            caught_type = "Exception"

        self.assertEqual("AuthenticationError", caught_type)

    def test_exception_message_propagation(self):
        message = "Specific error details for debugging"
        try:
            raise RepositorySyncError(message)
        except RepositorySyncError as exc:
            self.assertEqual(message, str(exc))


if __name__ == "__main__":
    unittest.main()