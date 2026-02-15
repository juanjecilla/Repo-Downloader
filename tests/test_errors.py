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
    def test_base_error_inherits_from_exception(self):
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


class TestErrorInstantiation(unittest.TestCase):
    def test_repo_downloader_error_with_message(self):
        error = RepoDownloaderError("test error message")
        self.assertEqual("test error message", str(error))

    def test_authentication_error_with_message(self):
        error = AuthenticationError("auth failed")
        self.assertEqual("auth failed", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_remote_api_error_with_message(self):
        error = RemoteAPIError("api request failed")
        self.assertEqual("api request failed", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_repository_sync_error_with_message(self):
        error = RepositorySyncError("sync failed")
        self.assertEqual("sync failed", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_run_lock_error_with_message(self):
        error = RunLockError("lock acquisition failed")
        self.assertEqual("lock acquisition failed", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_provider_configuration_error_with_message(self):
        error = ProviderConfigurationError("missing username")
        self.assertEqual("missing username", str(error))
        self.assertIsInstance(error, RepoDownloaderError)

    def test_provider_not_implemented_error_with_message(self):
        error = ProviderNotImplementedError("gitlab not ready")
        self.assertEqual("gitlab not ready", str(error))
        self.assertIsInstance(error, RepoDownloaderError)


class TestErrorCatching(unittest.TestCase):
    def test_catch_specific_error_as_base(self):
        try:
            raise AuthenticationError("auth failed")
        except RepoDownloaderError as exc:
            self.assertIsInstance(exc, AuthenticationError)
            self.assertEqual("auth failed", str(exc))

    def test_catch_base_error_does_not_catch_unrelated(self):
        with self.assertRaises(ValueError):
            try:
                raise ValueError("not a repo downloader error")
            except RepoDownloaderError:
                self.fail("Should not catch ValueError")


if __name__ == "__main__":
    unittest.main()