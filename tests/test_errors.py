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
            with self.subTest(error=error_class.__name__):
                self.assertTrue(issubclass(error_class, RepoDownloaderError))
                self.assertTrue(issubclass(error_class, Exception))

    def test_base_error_can_be_raised_with_message(self):
        with self.assertRaises(RepoDownloaderError) as context:
            raise RepoDownloaderError("base error message")
        self.assertEqual("base error message", str(context.exception))

    def test_provider_configuration_error(self):
        with self.assertRaises(ProviderConfigurationError) as context:
            raise ProviderConfigurationError("Missing username")
        self.assertIn("Missing username", str(context.exception))
        self.assertIsInstance(context.exception, RepoDownloaderError)

    def test_provider_not_implemented_error(self):
        with self.assertRaises(ProviderNotImplementedError) as context:
            raise ProviderNotImplementedError("Provider 'xyz' is not implemented yet.")
        self.assertIn("not implemented", str(context.exception))
        self.assertIsInstance(context.exception, RepoDownloaderError)

    def test_authentication_error(self):
        with self.assertRaises(AuthenticationError) as context:
            raise AuthenticationError("Invalid token")
        self.assertIn("Invalid token", str(context.exception))
        self.assertIsInstance(context.exception, RepoDownloaderError)

    def test_remote_api_error(self):
        with self.assertRaises(RemoteAPIError) as context:
            raise RemoteAPIError("API returned 500")
        self.assertIn("API returned 500", str(context.exception))
        self.assertIsInstance(context.exception, RepoDownloaderError)

    def test_repository_sync_error(self):
        with self.assertRaises(RepositorySyncError) as context:
            raise RepositorySyncError("Clone failed")
        self.assertIn("Clone failed", str(context.exception))
        self.assertIsInstance(context.exception, RepoDownloaderError)

    def test_run_lock_error(self):
        with self.assertRaises(RunLockError) as context:
            raise RunLockError("Lock already held")
        self.assertIn("Lock already held", str(context.exception))
        self.assertIsInstance(context.exception, RepoDownloaderError)

    def test_errors_can_be_caught_by_base_class(self):
        errors_to_test = [
            ProviderConfigurationError("config"),
            ProviderNotImplementedError("not impl"),
            AuthenticationError("auth"),
            RemoteAPIError("api"),
            RepositorySyncError("sync"),
            RunLockError("lock"),
        ]
        for error in errors_to_test:
            with self.subTest(error=type(error).__name__):
                try:
                    raise error
                except RepoDownloaderError:
                    pass
                else:
                    self.fail(f"{type(error).__name__} was not caught by RepoDownloaderError")

    def test_errors_preserve_cause_chain(self):
        original_error = ValueError("original cause")
        try:
            raise AuthenticationError("auth failed") from original_error
        except AuthenticationError as exc:
            self.assertEqual(original_error, exc.__cause__)
            self.assertIn("auth failed", str(exc))

    def test_errors_support_string_representation(self):
        error = RemoteAPIError("Request to 'https://api.example.com' failed")
        self.assertEqual("Request to 'https://api.example.com' failed", str(error))

    def test_errors_support_repr(self):
        error = RepositorySyncError("Failed cloning repository")
        repr_str = repr(error)
        self.assertIn("RepositorySyncError", repr_str)
        self.assertIn("Failed cloning repository", repr_str)


class TestErrorUsagePatterns(unittest.TestCase):
    def test_catch_specific_error_types(self):
        caught_errors = []

        def raise_auth_error():
            raise AuthenticationError("Token expired")

        def raise_api_error():
            raise RemoteAPIError("API timeout")

        try:
            raise_auth_error()
        except AuthenticationError as exc:
            caught_errors.append(type(exc).__name__)

        try:
            raise_api_error()
        except RemoteAPIError as exc:
            caught_errors.append(type(exc).__name__)

        self.assertEqual(["AuthenticationError", "RemoteAPIError"], caught_errors)

    def test_catch_multiple_error_types(self):
        def raise_various_errors(error_type):
            if error_type == "auth":
                raise AuthenticationError("auth error")
            if error_type == "api":
                raise RemoteAPIError("api error")
            if error_type == "sync":
                raise RepositorySyncError("sync error")

        for error_type in ("auth", "api", "sync"):
            with self.subTest(error_type=error_type):
                try:
                    raise_various_errors(error_type)
                except (AuthenticationError, RemoteAPIError, RepositorySyncError) as exc:
                    self.assertIsInstance(exc, RepoDownloaderError)

    def test_error_can_include_exception_context(self):
        original = ValueError("invalid value")
        try:
            try:
                raise original
            except ValueError as exc:
                raise RepositorySyncError(f"Sync failed: {exc}") from exc
        except RepositorySyncError as sync_error:
            self.assertIn("invalid value", str(sync_error))
            self.assertEqual(original, sync_error.__cause__)


if __name__ == "__main__":
    unittest.main()