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


    def test_not_implemented_provider_raises_on_all_methods(self):
        from data.source.remote_sources import _NotImplementedProvider
        provider = _NotImplementedProvider("azure")

        self.assertFalse(provider.auth_ok())
        self.assertIn("not implemented", provider.auth_error)

        from utils.errors import ProviderNotImplementedError
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_user_info()
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_repositories()
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_repository("workspace", "repo")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_branches("workspace/repo")


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestBitbucketSourceEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_request_timeout_raises_remote_api_error(self, session_cls):
        import requests
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            requests.Timeout("timeout"),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError
        with self.assertRaises(RemoteAPIError):
            source.list_repositories()

    @patch("data.source.remote_sources.requests.Session")
    def test_connection_error_raises_remote_api_error(self, session_cls):
        import requests
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            requests.ConnectionError("connection failed"),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError
        with self.assertRaises(RemoteAPIError):
            source.list_repositories()

    @patch("data.source.remote_sources.requests.Session")
    def test_403_status_raises_authentication_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(403, {"error": "forbidden"})]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        self.assertFalse(source.auth_ok())
        self.assertIn("403", source.auth_error)

    @patch("data.source.remote_sources.requests.Session")
    def test_500_status_raises_remote_api_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(500, {"error": "internal error"}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError
        with self.assertRaises(RemoteAPIError):
            source.list_repositories()

    @patch("data.source.remote_sources.requests.Session")
    def test_invalid_json_raises_remote_api_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, ValueError("invalid json")),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError
        with self.assertRaises(RemoteAPIError):
            source.list_repositories()

    @patch("data.source.remote_sources.requests.Session")
    def test_paginated_endpoint_missing_values_raises_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"unexpected": "no values key"}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError
        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()
        self.assertIn("did not include 'values'", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_repository_single_request(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"full_name": "acme/repo", "is_archived": False}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repo = source.get_repository("acme", "repo")
        self.assertEqual("acme/repo", repo["full_name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_list_branches_pagination(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                {"values": [{"name": "main"}], "next": "https://api.bitbucket.org/page-2"},
            ),
            _FakeResponse(200, {"values": [{"name": "dev"}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.list_branches("acme/repo")
        self.assertEqual(2, len(branches))
        self.assertEqual("main", branches[0]["name"])
        self.assertEqual("dev", branches[1]["name"])


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestGitHubSourceEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_non_list_paginated_response_raises_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, {"not": "a list"}),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        from utils.errors import RemoteAPIError
        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()
        self.assertIn("non-list payload", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_normalize_repository_adds_clone_links(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(
                200,
                {
                    "full_name": "acme/repo",
                    "ssh_url": "git@github.com:acme/repo.git",
                    "clone_url": "https://github.com/acme/repo.git",
                },
            ),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repo = source.get_repository("acme", "repo")
        clone_links = repo["links"]["clone"]
        self.assertEqual(2, len(clone_links))
        self.assertEqual("ssh", clone_links[0]["name"])
        self.assertEqual("https", clone_links[1]["name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_list_repositories_no_workspace_uses_user_repos(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, [{"full_name": "tester/repo"}]),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repos = source.list_repositories()
        requested_url = session.get.call_args_list[1].args[0]
        self.assertIn("/user/repos", requested_url)
        self.assertEqual(1, len(repos))


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestGitLabSourceEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_normalize_repository_adds_full_name_from_path_with_namespace(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                {
                    "path_with_namespace": "acme/services/repo",
                    "ssh_url_to_repo": "git@gitlab.com:acme/services/repo.git",
                    "http_url_to_repo": "https://gitlab.com/acme/services/repo.git",
                },
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repo = source.get_repository("acme/services", "repo")
        self.assertEqual("acme/services/repo", repo["full_name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_list_repositories_normalizes_all_repos(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [
                    {
                        "path_with_namespace": "acme/one",
                        "ssh_url_to_repo": "git@gitlab.com:acme/one.git",
                    },
                    {
                        "path_with_namespace": "acme/two",
                        "ssh_url_to_repo": "git@gitlab.com:acme/two.git",
                    },
                ],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repos = source.list_repositories()
        self.assertEqual(2, len(repos))
        self.assertEqual("acme/one", repos[0]["full_name"])
        self.assertEqual("acme/two", repos[1]["full_name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_pagination_with_invalid_next_page_header(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [{"path_with_namespace": "acme/one"}],
                headers={"X-Next-Page": "invalid"},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        from utils.errors import RemoteAPIError
        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()
        self.assertIn("Invalid pagination header", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_url_encoding_for_workspace_with_slash(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, [], headers={}),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        source.list_repositories(workspace="acme/services")
        requested_url = session.get.call_args_list[1].args[0]
        self.assertIn("acme%2Fservices", requested_url)


if __name__ == "__main__":
    unittest.main()