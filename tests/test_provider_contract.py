import importlib.util
import unittest

from data.source.provider_interface import RemoteProvider


REQUESTS_AVAILABLE = importlib.util.find_spec("requests") is not None


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider contract tests")
class TestProviderContract(unittest.TestCase):
    def test_provider_classes_implement_contract(self):
        from data.source.remote_sources import BitbucketSource, GitHubSource, GitLabSource

        for provider_class in (BitbucketSource, GitHubSource, GitLabSource):
            self.assertTrue(issubclass(provider_class, RemoteProvider))
            for method_name in (
                "get_user_info",
                "list_repositories",
                "get_repository",
                "list_branches",
                "auth_ok",
            ):
                self.assertTrue(callable(getattr(provider_class, method_name, None)))


if __name__ == "__main__":
    unittest.main()
