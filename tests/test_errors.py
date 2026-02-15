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
    def test_repo_downloader_error_is_base_exception(self):
        exc = RepoDownloaderError("base error")
        self.assertIsInstance(exc, Exception)
        self.assertEqual("base error", str(exc))

    def test_provider_configuration_error_inherits_from_base(self):
        exc = ProviderConfigurationError("config error")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertIsInstance(exc, Exception)
        self.assertEqual("config error", str(exc))

    def test_provider_not_implemented_error_inherits_from_base(self):
        exc = ProviderNotImplementedError("not implemented")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertIsInstance(exc, Exception)
        self.assertEqual("not implemented", str(exc))

    def test_authentication_error_inherits_from_base(self):
        exc = AuthenticationError("auth failed")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertIsInstance(exc, Exception)
        self.assertEqual("auth failed", str(exc))

    def test_remote_api_error_inherits_from_base(self):
        exc = RemoteAPIError("api error")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertIsInstance(exc, Exception)
        self.assertEqual("api error", str(exc))

    def test_repository_sync_error_inherits_from_base(self):
        exc = RepositorySyncError("sync failed")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertIsInstance(exc, Exception)
        self.assertEqual("sync failed", str(exc))

    def test_run_lock_error_inherits_from_base(self):
        exc = RunLockError("lock error")
        self.assertIsInstance(exc, RepoDownloaderError)
        self.assertIsInstance(exc, Exception)
        self.assertEqual("lock error", str(exc))


class TestExceptionRaising(unittest.TestCase):
    def test_repo_downloader_error_can_be_raised_and_caught(self):
        with self.assertRaises(RepoDownloaderError) as context:
            raise RepoDownloaderError("test error")
        self.assertEqual("test error", str(context.exception))

    def test_provider_configuration_error_can_be_caught_as_base(self):
        with self.assertRaises(RepoDownloaderError):
            raise ProviderConfigurationError("config problem")

    def test_authentication_error_can_be_caught_specifically(self):
        with self.assertRaises(AuthenticationError) as context:
            raise AuthenticationError("bad credentials")
        self.assertEqual("bad credentials", str(context.exception))

    def test_remote_api_error_can_be_caught_specifically(self):
        with self.assertRaises(RemoteAPIError) as context:
            raise RemoteAPIError("API returned 500")
        self.assertEqual("API returned 500", str(context.exception))

    def test_repository_sync_error_can_be_caught_specifically(self):
        with self.assertRaises(RepositorySyncError) as context:
            raise RepositorySyncError("git fetch failed")
        self.assertEqual("git fetch failed", str(context.exception))

    def test_run_lock_error_can_be_caught_specifically(self):
        with self.assertRaises(RunLockError) as context:
            raise RunLockError("lock file exists")
        self.assertEqual("lock file exists", str(context.exception))


class TestExceptionChaining(unittest.TestCase):
    def test_exception_chaining_preserves_cause(self):
        try:
            try:
                raise ValueError("original error")
            except ValueError as original:
                raise AuthenticationError("authentication failed") from original
        except AuthenticationError as exc:
            self.assertIsInstance(exc.__cause__, ValueError)
            self.assertEqual("original error", str(exc.__cause__))

    def test_repository_sync_error_chaining(self):
        try:
            try:
                raise OSError("disk full")
            except OSError as original:
                raise RepositorySyncError("failed to clone repository") from original
        except RepositorySyncError as exc:
            self.assertIsInstance(exc.__cause__, OSError)
            self.assertEqual("disk full", str(exc.__cause__))

    def test_remote_api_error_chaining(self):
        try:
            try:
                raise ConnectionError("network timeout")
            except ConnectionError as original:
                raise RemoteAPIError("API request failed") from original
        except RemoteAPIError as exc:
            self.assertIsInstance(exc.__cause__, ConnectionError)
            self.assertEqual("network timeout", str(exc.__cause__))


class TestExceptionMessages(unittest.TestCase):
    def test_empty_message_creates_empty_string(self):
        exc = RepoDownloaderError("")
        self.assertEqual("", str(exc))

    def test_multiline_message_preserved(self):
        message = "Line 1\nLine 2\nLine 3"
        exc = RepositorySyncError(message)
        self.assertEqual(message, str(exc))

    def test_message_with_special_characters(self):
        message = "Error: repo 'acme/test' failed with status 403"
        exc = RemoteAPIError(message)
        self.assertEqual(message, str(exc))

    def test_message_with_unicode(self):
        message = "Failed to clone repository: ñoño-répo"
        exc = RepositorySyncError(message)
        self.assertEqual(message, str(exc))


class TestExceptionCatching(unittest.TestCase):
    def test_catch_all_repo_downloader_errors_at_base_level(self):
        exceptions = [
            ProviderConfigurationError("config"),
            ProviderNotImplementedError("not impl"),
            AuthenticationError("auth"),
            RemoteAPIError("api"),
            RepositorySyncError("sync"),
            RunLockError("lock"),
        ]

        for exc_instance in exceptions:
            with self.subTest(exception_type=type(exc_instance).__name__):
                with self.assertRaises(RepoDownloaderError):
                    raise exc_instance

    def test_specific_exception_not_caught_by_other_types(self):
        with self.assertRaises(AuthenticationError):
            try:
                raise AuthenticationError("auth failed")
            except RemoteAPIError:
                self.fail("AuthenticationError should not be caught by RemoteAPIError")


if __name__ == "__main__":
    unittest.main()