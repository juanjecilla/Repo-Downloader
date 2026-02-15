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

    def test_all_errors_inherit_from_base(self):
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
                self.assertTrue(issubclass(error_class, RepoDownloaderError))

    def test_base_error_instantiation(self):
        error = RepoDownloaderError("Base error message")
        self.assertEqual("Base error message", str(error))

    def test_provider_configuration_error_with_message(self):
        error = ProviderConfigurationError("Missing username")
        self.assertEqual("Missing username", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_provider_not_implemented_error_with_message(self):
        error = ProviderNotImplementedError("Provider 'xyz' not implemented")
        self.assertEqual("Provider 'xyz' not implemented", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_authentication_error_with_message(self):
        error = AuthenticationError("Invalid credentials")
        self.assertEqual("Invalid credentials", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_remote_api_error_with_message(self):
        error = RemoteAPIError("API returned 500")
        self.assertEqual("API returned 500", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_repository_sync_error_with_message(self):
        error = RepositorySyncError("Clone failed")
        self.assertEqual("Clone failed", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_run_lock_error_with_message(self):
        error = RunLockError("Lock already held")
        self.assertEqual("Lock already held", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_errors_can_be_raised_and_caught_as_base(self):
        with self.assertRaises(RepoDownloaderError):
            raise AuthenticationError("Test error")

    def test_errors_can_be_raised_and_caught_specifically(self):
        with self.assertRaises(AuthenticationError):
            raise AuthenticationError("Test error")

    def test_error_with_nested_exception(self):
        try:
            try:
                raise ValueError("Original error")
            except ValueError as exc:
                raise RepositorySyncError("Sync failed due to value error") from exc
        except RepositorySyncError as sync_error:
            self.assertIsInstance(sync_error.__cause__, ValueError)
            self.assertEqual("Original error", str(sync_error.__cause__))

    def test_errors_preserve_traceback(self):
        try:
            raise RemoteAPIError("API failed at line 42")
        except RemoteAPIError as error:
            import traceback
            tb = traceback.format_exc()
            self.assertIn("RemoteAPIError", tb)
            self.assertIn("API failed at line 42", tb)

    def test_error_equality_based_on_message(self):
        error1 = AuthenticationError("Same message")
        error2 = AuthenticationError("Same message")
        # Exceptions are compared by identity, not value, so they should not be equal
        self.assertIsNot(error1, error2)
        # But their messages should be equal
        self.assertEqual(str(error1), str(error2))

    def test_error_with_empty_message(self):
        error = RemoteAPIError("")
        self.assertEqual("", str(error))

    def test_error_with_multiline_message(self):
        message = "Line 1\nLine 2\nLine 3"
        error = RepositorySyncError(message)
        self.assertEqual(message, str(error))

    def test_error_with_special_characters(self):
        message = "Error: repo 'acme/test-repo' failed (status=401)"
        error = AuthenticationError(message)
        self.assertIn("acme/test-repo", str(error))
        self.assertIn("status=401", str(error))

    def test_catching_multiple_error_types(self):
        for error_class in [AuthenticationError, RemoteAPIError, RepositorySyncError]:
            with self.subTest(error_class=error_class.__name__):
                with self.assertRaises((AuthenticationError, RemoteAPIError, RepositorySyncError)):
                    raise error_class("Test error")

    def test_error_repr_contains_message(self):
        error = ProviderConfigurationError("Config missing")
        repr_str = repr(error)
        self.assertIn("Config missing", repr_str)


class TestErrorUsagePatterns(unittest.TestCase):
    def test_chaining_provider_configuration_error(self):
        try:
            try:
                raise ImportError("Missing module")
            except ImportError as exc:
                raise ProviderConfigurationError("Provider not available") from exc
        except ProviderConfigurationError as error:
            self.assertIsInstance(error.__cause__, ImportError)

    def test_chaining_authentication_error(self):
        try:
            try:
                raise ConnectionError("Network unreachable")
            except ConnectionError as exc:
                raise AuthenticationError("Cannot authenticate") from exc
        except AuthenticationError as error:
            self.assertIsInstance(error.__cause__, ConnectionError)

    def test_chaining_remote_api_error(self):
        try:
            try:
                raise ValueError("Invalid JSON")
            except ValueError as exc:
                raise RemoteAPIError("API response invalid") from exc
        except RemoteAPIError as error:
            self.assertIsInstance(error.__cause__, ValueError)

    def test_repository_sync_error_from_git_error(self):
        class FakeGitError(Exception):
            pass

        try:
            try:
                raise FakeGitError("Git command failed")
            except FakeGitError as exc:
                raise RepositorySyncError("Failed cloning repository") from exc
        except RepositorySyncError as error:
            self.assertIsInstance(error.__cause__, FakeGitError)

    def test_run_lock_error_from_os_error(self):
        try:
            try:
                raise OSError("Permission denied")
            except OSError as exc:
                raise RunLockError("Cannot acquire lock") from exc
        except RunLockError as error:
            self.assertIsInstance(error.__cause__, OSError)


if __name__ == "__main__":
    unittest.main()