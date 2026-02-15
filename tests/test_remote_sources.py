import importlib.util
import unittest
from unittest.mock import Mock, patch

REQUESTS_AVAILABLE = importlib.util.find_spec("requests") is not None
if REQUESTS_AVAILABLE:
    from data.source.remote_sources import BitbucketSource, GitHubSource, GitLabSource
else:
    BitbucketSource = None
    GitHubSource = None
    GitLabSource = None


class _FakeResponse:
    def __init__(self, status_code, payload, links=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.links = links or {}
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestBitbucketSource(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_pagination_collects_all_pages(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                {
                    "values": [{"repository": {"full_name": "acme/one"}}],
                    "next": "https://api.bitbucket.org/page-2",
                },
            ),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/two"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repositories = source.list_repositories(role="member")

        self.assertEqual(2, len(repositories))
        self.assertTrue(source.auth_ok())

    @patch("data.source.remote_sources.requests.Session")
    def test_workspace_filtering_applies_to_permissions_list(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                {
                    "values": [
                        {"repository": {"full_name": "acme/one"}},
                        {"repository": {"full_name": "other/two"}},
                    ]
                },
            ),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repositories = source.list_repositories(workspace="acme", role="member")

        self.assertEqual(1, len(repositories))
        self.assertEqual("acme/one", repositories[0]["repository"]["full_name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_auth_failure_sets_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(401, {"error": {}})]
        session_cls.return_value = session

        source = BitbucketSource("user", "bad-token")

        self.assertFalse(source.auth_ok())
        self.assertIn("Authentication failed", source.auth_error)


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestGitHubSource(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_pagination_collects_all_pages(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(
                200,
                [{"full_name": "acme/one"}],
                links={"next": {"url": "https://api.github.com/user/repos?page=2"}},
            ),
            _FakeResponse(200, [{"full_name": "acme/two"}]),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual(2, len(repositories))
        self.assertEqual("acme/one", repositories[0]["full_name"])
        self.assertTrue(source.auth_ok())

    @patch("data.source.remote_sources.requests.Session")
    def test_workspace_filter_uses_org_endpoint(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, [{"full_name": "acme/one"}]),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repositories = source.list_repositories(workspace="acme")

        self.assertEqual(1, len(repositories))
        requested_url = session.get.call_args_list[1].args[0]
        self.assertIn("/orgs/acme/repos", requested_url)

    @patch("data.source.remote_sources.requests.Session")
    def test_get_repository_normalizes_clone_links(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(
                200,
                {
                    "full_name": "acme/service",
                    "ssh_url": "git@github.com:acme/service.git",
                    "clone_url": "https://github.com/acme/service.git",
                    "archived": False,
                },
            ),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repository = source.get_repository("acme", "service")

        clone_links = repository["links"]["clone"]
        self.assertEqual("ssh", clone_links[0]["name"])
        self.assertEqual("git@github.com:acme/service.git", clone_links[0]["href"])

    @patch("data.source.remote_sources.requests.Session")
    def test_auth_failure_sets_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(401, {"message": "Bad credentials"})]
        session_cls.return_value = session

        source = GitHubSource("user", "bad-token")

        self.assertFalse(source.auth_ok())
        self.assertIn("Authentication failed", source.auth_error)


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestGitLabSource(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_pagination_collects_all_pages(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [
                    {
                        "path_with_namespace": "acme/one",
                        "ssh_url_to_repo": "git@gitlab.com:acme/one.git",
                        "http_url_to_repo": "https://gitlab.com/acme/one.git",
                    }
                ],
                headers={"X-Next-Page": "2"},
            ),
            _FakeResponse(
                200,
                [
                    {
                        "path_with_namespace": "acme/two",
                        "ssh_url_to_repo": "git@gitlab.com:acme/two.git",
                        "http_url_to_repo": "https://gitlab.com/acme/two.git",
                    }
                ],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual(2, len(repositories))
        self.assertEqual("acme/one", repositories[0]["full_name"])
        self.assertTrue(source.auth_ok())

    @patch("data.source.remote_sources.requests.Session")
    def test_workspace_filter_uses_group_endpoint(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [{"path_with_namespace": "acme/services/api"}],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repositories = source.list_repositories(workspace="acme/services")

        self.assertEqual(1, len(repositories))
        requested_url = session.get.call_args_list[1].args[0]
        self.assertIn("/groups/acme%2Fservices/projects", requested_url)

    @patch("data.source.remote_sources.requests.Session")
    def test_get_repository_normalizes_clone_links(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                {
                    "path_with_namespace": "acme/service",
                    "ssh_url_to_repo": "git@gitlab.com:acme/service.git",
                    "http_url_to_repo": "https://gitlab.com/acme/service.git",
                    "archived": False,
                },
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repository = source.get_repository("acme", "service")

        clone_links = repository["links"]["clone"]
        self.assertEqual("ssh", clone_links[0]["name"])
        self.assertEqual("git@gitlab.com:acme/service.git", clone_links[0]["href"])

    @patch("data.source.remote_sources.requests.Session")
    def test_auth_failure_sets_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(401, {"message": "Unauthorized"})]
        session_cls.return_value = session

        source = GitLabSource("user", "bad-token")

        self.assertFalse(source.auth_ok())
        self.assertIn("Authentication failed", source.auth_error)


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestRemoteSourcesErrorHandling(unittest.TestCase):
    """Test error handling across all remote source providers."""

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_invalid_json_response(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, ValueError("Invalid JSON")),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError
        source = BitbucketSource("user", "token")
        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()
        self.assertIn("Invalid JSON", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_github_handles_invalid_json_response(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, ValueError("Invalid JSON")),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError
        source = GitHubSource("user", "token")
        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()
        self.assertIn("Invalid JSON", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_handles_invalid_json_response(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, ValueError("Invalid JSON")),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError
        source = GitLabSource("user", "token")
        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()
        self.assertIn("Invalid JSON", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_403_forbidden(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(403, {"error": "forbidden"})]
        session_cls.return_value = session

        from utils.errors import AuthenticationError
        source = BitbucketSource("user", "token")
        self.assertFalse(source.auth_ok())
        self.assertIsNotNone(source.auth_error)

    @patch("data.source.remote_sources.requests.Session")
    def test_github_handles_500_server_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(500, {"error": "server error"}),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError
        source = GitHubSource("user", "token")
        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()
        self.assertIn("500", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_network_timeout(self, session_cls):
        import requests
        session = Mock()
        session.get.side_effect = requests.Timeout("Connection timeout")
        session_cls.return_value = session

        from utils.errors import RemoteAPIError
        source = BitbucketSource("user", "token")
        with self.assertRaises(RemoteAPIError) as context:
            source.get_user_info()
        self.assertIn("timeout", str(context.exception).lower())

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_handles_invalid_pagination_header(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, [{"path_with_namespace": "acme/one"}], headers={"X-Next-Page": "invalid"}),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError
        source = GitLabSource("user", "token")
        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()
        self.assertIn("pagination", str(context.exception).lower())


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestNotImplementedProvider(unittest.TestCase):
    """Test the _NotImplementedProvider stub class."""

    def test_not_implemented_provider_reports_not_implemented(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("test-provider")
        self.assertFalse(provider.auth_ok())
        self.assertIn("test-provider", provider.auth_error)
        self.assertIn("not implemented", provider.auth_error.lower())

    def test_not_implemented_provider_raises_on_get_user_info(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("test-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_user_info()

    def test_not_implemented_provider_raises_on_list_repositories(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("test-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_repositories()

    def test_not_implemented_provider_raises_on_get_repository(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("test-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_repository("workspace", "name")

    def test_not_implemented_provider_raises_on_list_branches(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("test-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_branches("full/name")


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestBitbucketLegacyAliases(unittest.TestCase):
    """Test legacy compatibility methods in BitbucketSource."""

    @patch("data.source.remote_sources.requests.Session")
    def test_get_repo_list_calls_list_repositories(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/repo"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repos = source.get_repo_list(workspace="acme", paginated=True)

        self.assertEqual(1, len(repos))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_repositories_by_permission_calls_list_repositories(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/repo"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repos = source.get_repositories_by_permission(role="admin")

        self.assertEqual(1, len(repos))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_branches_calls_list_branches(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"name": "main"}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.get_branches("acme/repo")

        self.assertEqual(1, len(branches))


if __name__ == "__main__":
    unittest.main()