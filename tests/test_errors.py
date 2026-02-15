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


class TestErrorExceptions(unittest.TestCase):
    def test_base_exception_is_exception(self):
        self.assertTrue(issubclass(RepoDownloaderError, Exception))

    def test_base_exception_can_be_raised(self):
        with self.assertRaises(RepoDownloaderError) as ctx:
            raise RepoDownloaderError("base error")
        self.assertEqual("base error", str(ctx.exception))

    def test_provider_configuration_error_inherits_from_base(self):
        self.assertTrue(issubclass(ProviderConfigurationError, RepoDownloaderError))

    def test_provider_configuration_error_can_be_raised(self):
        with self.assertRaises(ProviderConfigurationError) as ctx:
            raise ProviderConfigurationError("config missing")
        self.assertEqual("config missing", str(ctx.exception))

    def test_provider_not_implemented_error_inherits_from_base(self):
        self.assertTrue(issubclass(ProviderNotImplementedError, RepoDownloaderError))

    def test_provider_not_implemented_error_can_be_raised(self):
        with self.assertRaises(ProviderNotImplementedError) as ctx:
            raise ProviderNotImplementedError("not implemented")
        self.assertEqual("not implemented", str(ctx.exception))

    def test_authentication_error_inherits_from_base(self):
        self.assertTrue(issubclass(AuthenticationError, RepoDownloaderError))

    def test_authentication_error_can_be_raised(self):
        with self.assertRaises(AuthenticationError) as ctx:
            raise AuthenticationError("invalid token")
        self.assertEqual("invalid token", str(ctx.exception))

    def test_remote_api_error_inherits_from_base(self):
        self.assertTrue(issubclass(RemoteAPIError, RepoDownloaderError))

    def test_remote_api_error_can_be_raised(self):
        with self.assertRaises(RemoteAPIError) as ctx:
            raise RemoteAPIError("API request failed")
        self.assertEqual("API request failed", str(ctx.exception))

    def test_repository_sync_error_inherits_from_base(self):
        self.assertTrue(issubclass(RepositorySyncError, RepoDownloaderError))

    def test_repository_sync_error_can_be_raised(self):
        with self.assertRaises(RepositorySyncError) as ctx:
            raise RepositorySyncError("clone failed")
        self.assertEqual("clone failed", str(ctx.exception))

    def test_run_lock_error_inherits_from_base(self):
        self.assertTrue(issubclass(RunLockError, RepoDownloaderError))

    def test_run_lock_error_can_be_raised(self):
        with self.assertRaises(RunLockError) as ctx:
            raise RunLockError("lock active")
        self.assertEqual("lock active", str(ctx.exception))

    def test_catch_base_exception_catches_all_subclasses(self):
        exceptions = [
            ProviderConfigurationError("config"),
            ProviderNotImplementedError("not impl"),
            AuthenticationError("auth"),
            RemoteAPIError("api"),
            RepositorySyncError("sync"),
            RunLockError("lock"),
        ]

        for exc in exceptions:
            with self.assertRaises(RepoDownloaderError):
                raise exc

    def test_catch_specific_exception_does_not_catch_siblings(self):
        with self.assertRaises(AuthenticationError):
            try:
                raise AuthenticationError("auth failed")
            except RemoteAPIError:
                self.fail("Should not catch RemoteAPIError")

    def test_exception_with_chained_cause(self):
        try:
            try:
                raise ValueError("original error")
            except ValueError as exc:
                raise RepositorySyncError("sync failed") from exc
        except RepositorySyncError as sync_exc:
            self.assertEqual("sync failed", str(sync_exc))
            self.assertIsInstance(sync_exc.__cause__, ValueError)
            self.assertEqual("original error", str(sync_exc.__cause__))


if __name__ == "__main__":
    unittest.main()