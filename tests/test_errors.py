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
        """Verify all custom errors inherit from RepoDownloaderError."""
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

    def test_base_exception_inherits_from_exception(self):
        """Verify RepoDownloaderError inherits from Exception."""
        self.assertTrue(issubclass(RepoDownloaderError, Exception))

    def test_errors_can_be_instantiated_with_message(self):
        """Verify all error classes can be instantiated with a message."""
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
            with self.subTest(error_class=error_class.__name__):
                error = error_class("test message")
                self.assertEqual("test message", str(error))

    def test_errors_can_be_raised_and_caught_as_base_class(self):
        """Verify errors can be caught as RepoDownloaderError."""
        with self.assertRaises(RepoDownloaderError):
            raise AuthenticationError("auth failed")

    def test_provider_configuration_error_distinguishable(self):
        """Verify ProviderConfigurationError is distinct from other errors."""
        error = ProviderConfigurationError("missing username")
        self.assertIsInstance(error, ProviderConfigurationError)
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertNotIsInstance(error, AuthenticationError)

    def test_provider_not_implemented_error_distinguishable(self):
        """Verify ProviderNotImplementedError is distinct from other errors."""
        error = ProviderNotImplementedError("gitlab not implemented")
        self.assertIsInstance(error, ProviderNotImplementedError)
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertNotIsInstance(error, ProviderConfigurationError)

    def test_authentication_error_distinguishable(self):
        """Verify AuthenticationError is distinct from other errors."""
        error = AuthenticationError("invalid token")
        self.assertIsInstance(error, AuthenticationError)
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertNotIsInstance(error, RemoteAPIError)

    def test_remote_api_error_distinguishable(self):
        """Verify RemoteAPIError is distinct from other errors."""
        error = RemoteAPIError("API request failed")
        self.assertIsInstance(error, RemoteAPIError)
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertNotIsInstance(error, AuthenticationError)

    def test_repository_sync_error_distinguishable(self):
        """Verify RepositorySyncError is distinct from other errors."""
        error = RepositorySyncError("clone failed")
        self.assertIsInstance(error, RepositorySyncError)
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertNotIsInstance(error, RemoteAPIError)

    def test_run_lock_error_distinguishable(self):
        """Verify RunLockError is distinct from other errors."""
        error = RunLockError("lock already acquired")
        self.assertIsInstance(error, RunLockError)
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertNotIsInstance(error, RepositorySyncError)

    def test_errors_support_exception_chaining(self):
        """Verify errors support exception chaining with 'from' clause."""
        original = ValueError("original error")
        try:
            try:
                raise original
            except ValueError as exc:
                raise RemoteAPIError("wrapped error") from exc
        except RemoteAPIError as caught:
            self.assertEqual("wrapped error", str(caught))
            self.assertIsInstance(caught.__cause__, ValueError)
            self.assertEqual("original error", str(caught.__cause__))

    def test_errors_can_be_caught_by_specific_type(self):
        """Verify errors can be caught by their specific type."""
        caught_error = None
        try:
            raise RepositorySyncError("sync failed")
        except RepositorySyncError as exc:
            caught_error = exc

        self.assertIsNotNone(caught_error)
        self.assertEqual("sync failed", str(caught_error))

    def test_multiple_error_types_can_be_caught_together(self):
        """Verify multiple error types can be caught in one except block."""
        for error_class in (AuthenticationError, RemoteAPIError):
            with self.subTest(error_class=error_class.__name__):
                caught = False
                try:
                    raise error_class("error")
                except (AuthenticationError, RemoteAPIError):
                    caught = True
                self.assertTrue(caught)

    def test_error_messages_are_preserved(self):
        """Verify error messages are preserved correctly."""
        message = "This is a detailed error message with special chars: !@#$%"
        error = ProviderConfigurationError(message)
        self.assertEqual(message, str(error))

    def test_empty_error_message(self):
        """Verify errors can be created with empty messages."""
        error = RepoDownloaderError("")
        self.assertEqual("", str(error))

    def test_error_with_multiline_message(self):
        """Verify errors handle multiline messages correctly."""
        message = "Line 1\nLine 2\nLine 3"
        error = RepositorySyncError(message)
        self.assertEqual(message, str(error))


class TestErrorUsagePatterns(unittest.TestCase):
    def test_classifying_errors_in_exception_handler(self):
        """Verify errors can be classified in exception handlers."""
        def classify_error(exc):
            if isinstance(exc, AuthenticationError):
                return "auth"
            if isinstance(exc, RemoteAPIError):
                return "api"
            if isinstance(exc, RepositorySyncError):
                return "sync"
            return "other"

        self.assertEqual("auth", classify_error(AuthenticationError("test")))
        self.assertEqual("api", classify_error(RemoteAPIError("test")))
        self.assertEqual("sync", classify_error(RepositorySyncError("test")))
        self.assertEqual("other", classify_error(ValueError("test")))

    def test_catching_base_error_allows_specific_handling(self):
        """Verify catching base error allows for specific type checks."""
        errors_raised = []
        for error in [
            AuthenticationError("auth"),
            RemoteAPIError("api"),
            RepositorySyncError("sync"),
        ]:
            try:
                raise error
            except RepoDownloaderError as exc:
                errors_raised.append(type(exc).__name__)

        self.assertEqual(
            ["AuthenticationError", "RemoteAPIError", "RepositorySyncError"],
            errors_raised,
        )

    def test_error_context_preserved_in_chained_exceptions(self):
        """Verify error context is preserved when chaining exceptions."""
        try:
            try:
                raise KeyError("missing key")
            except KeyError as exc:
                raise RemoteAPIError("API returned invalid data") from exc
        except RemoteAPIError as caught:
            self.assertIsNotNone(caught.__cause__)
            self.assertIsInstance(caught.__cause__, KeyError)


if __name__ == "__main__":
    unittest.main()