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

    @patch("data.source.remote_sources.requests.Session")
    def test_list_branches_paginated(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [{"name": "main"}, {"name": "dev"}],
                headers={"X-Next-Page": "2"},
            ),
            _FakeResponse(200, [{"name": "feature/x"}], headers={}),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        branches = source.list_branches("acme/repo")

        self.assertEqual(3, len(branches))
        self.assertEqual("main", branches[0]["name"])
        self.assertEqual("dev", branches[1]["name"])
        self.assertEqual("feature/x", branches[2]["name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_source_normalizes_full_name_from_path_with_namespace(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [
                    {
                        "path_with_namespace": "acme/services/api",
                        "ssh_url_to_repo": "git@gitlab.com:acme/services/api.git",
                    }
                ],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual("acme/services/api", repositories[0]["full_name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_legacy_get_repo_list_compatibility(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/one"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repositories = source.get_repo_list(workspace="acme", paginated=True)

        self.assertEqual(1, len(repositories))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_legacy_get_repositories_by_permission(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/one"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repositories = source.get_repositories_by_permission(role="admin")

        self.assertEqual(1, len(repositories))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_legacy_get_branches_alias(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"name": "main"}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.get_branches("acme/repo")

        self.assertEqual(1, len(branches))


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_empty_pagination_values(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": []}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual(0, len(repositories))

    @patch("data.source.remote_sources.requests.Session")
    def test_github_handles_empty_list_response(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, []),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual(0, len(repositories))

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_handles_invalid_pagination_header(self, session_cls):
        from utils.errors import RemoteAPIError

        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, [{"path_with_namespace": "acme/one"}], headers={"X-Next-Page": "invalid"}),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")

        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()

        self.assertIn("Invalid pagination header", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_handles_missing_next_url_gracefully(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/one"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual(1, len(repositories))

    @patch("data.source.remote_sources.requests.Session")
    def test_github_handles_missing_links_header_gracefully(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, [{"full_name": "acme/one"}]),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual(1, len(repositories))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_request_timeout_raises_remote_api_error(self, session_cls):
        import requests
        from utils.errors import RemoteAPIError

        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            requests.Timeout("Connection timed out"),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")

        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()

        self.assertIn("failed", str(context.exception).lower())

    @patch("data.source.remote_sources.requests.Session")
    def test_github_handles_403_forbidden_as_auth_error(self, session_cls):
        from utils.errors import AuthenticationError

        session = Mock()
        session.get.side_effect = [_FakeResponse(403, {"message": "Forbidden"})]
        session_cls.return_value = session

        source = GitHubSource("user", "token")

        self.assertFalse(source.auth_ok())
        self.assertIn("Authentication failed", source.auth_error)

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_handles_500_server_error(self, session_cls):
        from utils.errors import RemoteAPIError

        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(500, {"error": "Internal Server Error"}),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")

        with self.assertRaises(RemoteAPIError) as context:
            source.list_repositories()

        self.assertIn("500", str(context.exception))


if __name__ == "__main__":
    unittest.main()