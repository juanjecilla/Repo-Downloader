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
class TestNotImplementedProvider(unittest.TestCase):
    def test_not_implemented_provider_reports_auth_error(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("custom-provider")
        self.assertFalse(provider.auth_ok())
        self.assertIn("custom-provider", provider.auth_error)
        self.assertIn("not implemented", provider.auth_error)

    def test_not_implemented_provider_raises_on_get_user_info(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("custom-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_user_info()

    def test_not_implemented_provider_raises_on_list_repositories(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("custom-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_repositories()

    def test_not_implemented_provider_raises_on_get_repository(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("custom-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_repository("workspace", "repo")

    def test_not_implemented_provider_raises_on_list_branches(self):
        from data.source.remote_sources import _NotImplementedProvider
        from utils.errors import ProviderNotImplementedError

        provider = _NotImplementedProvider("custom-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_branches("workspace/repo")


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestRemoteSourcesEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_request_exception(self, session_cls):
        import requests
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            requests.RequestException("network error"),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError

        source = BitbucketSource("user", "token")
        with self.assertRaises(RemoteAPIError) as ctx:
            source.list_repositories()
        self.assertIn("network error", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_json_decode_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, ValueError("invalid json")),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError

        source = BitbucketSource("user", "token")
        with self.assertRaises(RemoteAPIError) as ctx:
            source.list_repositories()
        self.assertIn("Invalid JSON", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_403_forbidden(self, session_cls):
        session = Mock()
        # First call for get_user_info, second for list_repositories
        session.get.side_effect = [
            _FakeResponse(403, {"error": "forbidden"}),
            _FakeResponse(403, {"error": "forbidden"}),
        ]
        session_cls.return_value = session

        from utils.errors import AuthenticationError

        source = BitbucketSource("user", "bad-token")
        self.assertFalse(source.auth_ok())
        with self.assertRaises(AuthenticationError):
            source.list_repositories()

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_500_server_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(500, {"error": "server error"}),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError

        source = BitbucketSource("user", "token")
        with self.assertRaises(RemoteAPIError) as ctx:
            source.list_repositories()
        self.assertIn("status 500", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_github_normalizes_repository_clone_links(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(
                200,
                {
                    "full_name": "acme/service",
                    "ssh_url": "git@github.com:acme/service.git",
                    "clone_url": "https://github.com/acme/service.git",
                },
            ),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repo = source.get_repository("acme", "service")

        self.assertIn("links", repo)
        self.assertIn("clone", repo["links"])
        clone_links = repo["links"]["clone"]
        self.assertEqual(2, len(clone_links))
        ssh_link = next((link for link in clone_links if link["name"] == "ssh"), None)
        self.assertIsNotNone(ssh_link)
        self.assertEqual("git@github.com:acme/service.git", ssh_link["href"])

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_normalizes_full_name_from_path_with_namespace(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [
                    {
                        "path_with_namespace": "acme/repo",
                        "ssh_url_to_repo": "git@gitlab.com:acme/repo.git",
                    }
                ],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repos = source.list_repositories()

        self.assertEqual(1, len(repos))
        self.assertEqual("acme/repo", repos[0]["full_name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_handles_invalid_pagination_header(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, [{"path_with_namespace": "acme/repo"}], headers={"X-Next-Page": "invalid"}),
        ]
        session_cls.return_value = session

        from utils.errors import RemoteAPIError

        source = GitLabSource("user", "token")
        with self.assertRaises(RemoteAPIError) as ctx:
            source.list_repositories()
        self.assertIn("Invalid pagination header", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_url_encodes_workspace_in_group_endpoint(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, [], headers={}),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        source.list_repositories(workspace="acme/subgroup")

        # Verify the URL was encoded
        requested_url = session.get.call_args_list[1].args[0]
        self.assertIn("acme%2Fsubgroup", requested_url)

    @patch("data.source.remote_sources.requests.Session")
    def test_all_providers_have_current_user_property(self, session_cls):
        session = Mock()
        session.get.return_value = _FakeResponse(200, {"username": "tester", "login": "tester"})
        session_cls.return_value = session

        for provider_class in (BitbucketSource, GitHubSource, GitLabSource):
            with self.subTest(provider=provider_class.provider_name):
                provider = provider_class("user", "token")
                self.assertIsNotNone(provider.current_user)


if __name__ == "__main__":
    unittest.main()