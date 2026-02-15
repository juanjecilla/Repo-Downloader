import unittest

from utils.errors import (
    AuthenticationError,
    ProviderConfigurationError,
    ProviderNotImplementedError,
    RemoteAPIError,
    RepoDownloaderError,
    RepositorySyncError,
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


class TestRepoDownloaderError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(RepoDownloaderError) as context:
            raise RepoDownloaderError("Test error message")
        self.assertEqual("Test error message", str(context.exception))

    def test_can_be_raised_without_message(self):
        with self.assertRaises(RepoDownloaderError):
            raise RepoDownloaderError()

    def test_can_be_caught_as_exception(self):
        try:
            raise RepoDownloaderError("Test")
        except Exception as exc:
            self.assertIsInstance(exc, RepoDownloaderError)


class TestProviderConfigurationError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(ProviderConfigurationError) as context:
            raise ProviderConfigurationError("Missing configuration")
        self.assertEqual("Missing configuration", str(context.exception))

    def test_can_be_caught_as_base_error(self):
        try:
            raise ProviderConfigurationError("Test")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, ProviderConfigurationError)


class TestProviderNotImplementedError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(ProviderNotImplementedError) as context:
            raise ProviderNotImplementedError("Provider not implemented")
        self.assertEqual("Provider not implemented", str(context.exception))

    def test_can_be_caught_as_base_error(self):
        try:
            raise ProviderNotImplementedError("Test")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, ProviderNotImplementedError)


class TestAuthenticationError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(AuthenticationError) as context:
            raise AuthenticationError("Authentication failed")
        self.assertEqual("Authentication failed", str(context.exception))

    def test_can_be_caught_as_base_error(self):
        try:
            raise AuthenticationError("Test")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, AuthenticationError)


class TestRemoteAPIError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(RemoteAPIError) as context:
            raise RemoteAPIError("API request failed")
        self.assertEqual("API request failed", str(context.exception))

    def test_can_be_caught_as_base_error(self):
        try:
            raise RemoteAPIError("Test")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, RemoteAPIError)


class TestRepositorySyncError(unittest.TestCase):
    def test_can_be_raised_with_message(self):
        with self.assertRaises(RepositorySyncError) as context:
            raise RepositorySyncError("Sync failed")
        self.assertEqual("Sync failed", str(context.exception))

    def test_can_be_caught_as_base_error(self):
        try:
            raise RepositorySyncError("Test")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, RepositorySyncError)


class TestErrorChaining(unittest.TestCase):
    def test_errors_support_exception_chaining(self):
        original = ValueError("Original error")
        try:
            try:
                raise original
            except ValueError as exc:
                raise ProviderConfigurationError("Wrapped error") from exc
        except ProviderConfigurationError as chained:
            self.assertIsInstance(chained.__cause__, ValueError)
            self.assertEqual("Original error", str(chained.__cause__))

    def test_multiple_error_types_can_be_caught_separately(self):
        caught_types = []

        for error_class in [
            AuthenticationError,
            RemoteAPIError,
            RepositorySyncError,
        ]:
            try:
                raise error_class("Test")
            except AuthenticationError:
                caught_types.append("auth")
            except RemoteAPIError:
                caught_types.append("api")
            except RepositorySyncError:
                caught_types.append("sync")

        self.assertEqual(["auth", "api", "sync"], caught_types)


if __name__ == "__main__":
    unittest.main()