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
    def test_base_exception_is_repo_downloader_error(self):
        error = RepoDownloaderError("base error")
        self.assertIsInstance(error, Exception)
        self.assertEqual("base error", str(error))

    def test_provider_configuration_error_inherits_from_base(self):
        error = ProviderConfigurationError("config error")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertIsInstance(error, Exception)
        self.assertEqual("config error", str(error))

    def test_provider_not_implemented_error_inherits_from_base(self):
        error = ProviderNotImplementedError("not implemented")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("not implemented", str(error))

    def test_authentication_error_inherits_from_base(self):
        error = AuthenticationError("auth failed")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("auth failed", str(error))

    def test_remote_api_error_inherits_from_base(self):
        error = RemoteAPIError("api error")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("api error", str(error))

    def test_repository_sync_error_inherits_from_base(self):
        error = RepositorySyncError("sync error")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("sync error", str(error))

    def test_run_lock_error_inherits_from_base(self):
        error = RunLockError("lock error")
        self.assertIsInstance(error, RepoDownloaderError)
        self.assertEqual("lock error", str(error))

    def test_errors_can_be_raised_and_caught_as_base_type(self):
        errors = [
            ProviderConfigurationError("config"),
            ProviderNotImplementedError("not implemented"),
            AuthenticationError("auth"),
            RemoteAPIError("api"),
            RepositorySyncError("sync"),
            RunLockError("lock"),
        ]
        for error in errors:
            with self.assertRaises(RepoDownloaderError):
                raise error

    def test_errors_can_be_caught_by_specific_type(self):
        with self.assertRaises(AuthenticationError) as context:
            raise AuthenticationError("specific auth error")
        self.assertEqual("specific auth error", str(context.exception))

    def test_error_messages_can_contain_detailed_information(self):
        error = RepositorySyncError(
            "Failed cloning repository from git@example.com:user/repo.git: "
            "Permission denied (publickey)"
        )
        self.assertIn("git@example.com:user/repo.git", str(error))
        self.assertIn("Permission denied", str(error))

    def test_errors_can_be_chained_with_context(self):
        try:
            try:
                raise ValueError("original error")
            except ValueError as exc:
                raise RemoteAPIError("wrapped error") from exc
        except RemoteAPIError as final_exc:
            self.assertEqual("wrapped error", str(final_exc))
            self.assertIsInstance(final_exc.__cause__, ValueError)
            self.assertEqual("original error", str(final_exc.__cause__))


if __name__ == "__main__":
    unittest.main()