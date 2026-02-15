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
    def test_list_branches_uses_url_encoding(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [{"name": "main"}, {"name": "dev"}],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        branches = source.list_branches("group/subgroup/project")

        self.assertEqual(2, len(branches))
        requested_url = session.get.call_args_list[1].args[0]
        self.assertIn("group%2Fsubgroup%2Fproject", requested_url)

    @patch("data.source.remote_sources.requests.Session")
    def test_get_repository_with_nested_groups(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                {
                    "path_with_namespace": "group/subgroup/service",
                    "ssh_url_to_repo": "git@gitlab.com:group/subgroup/service.git",
                    "http_url_to_repo": "https://gitlab.com/group/subgroup/service.git",
                    "archived": False,
                },
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repository = source.get_repository("group/subgroup", "service")

        self.assertEqual("group/subgroup/service", repository["full_name"])
        requested_url = session.get.call_args_list[1].args[0]
        self.assertIn("group%2Fsubgroup%2Fservice", requested_url)

    @patch("data.source.remote_sources.requests.Session")
    def test_list_repositories_includes_subgroups(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [
                    {
                        "path_with_namespace": "group/project1",
                        "ssh_url_to_repo": "git@gitlab.com:group/project1.git",
                        "http_url_to_repo": "https://gitlab.com/group/project1.git",
                    },
                    {
                        "path_with_namespace": "group/subgroup/project2",
                        "ssh_url_to_repo": "git@gitlab.com:group/subgroup/project2.git",
                        "http_url_to_repo": "https://gitlab.com/group/subgroup/project2.git",
                    },
                ],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repositories = source.list_repositories(workspace="group")

        self.assertEqual(2, len(repositories))
        # Verify include_subgroups parameter was sent
        call_params = session.get.call_args_list[1].kwargs.get("params", {})
        self.assertEqual("true", call_params.get("include_subgroups"))

    @patch("data.source.remote_sources.requests.Session")
    def test_normalize_repository_payload_adds_full_name(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [
                    {
                        "path_with_namespace": "acme/repo",
                        "ssh_url_to_repo": "git@gitlab.com:acme/repo.git",
                        "http_url_to_repo": "https://gitlab.com/acme/repo.git",
                    }
                ],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual("acme/repo", repositories[0]["full_name"])
        self.assertIn("links", repositories[0])
        self.assertIn("clone", repositories[0]["links"])


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider edge case tests")
class TestProviderEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_request_json_raises_on_timeout(self, session_cls):
        from data.source.remote_sources import BitbucketSource
        import requests

        session = Mock()
        session.get.side_effect = requests.Timeout("Connection timeout")
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        self.assertIsNone(source._current_user)
        self.assertIsNotNone(source.auth_error)

    @patch("data.source.remote_sources.requests.Session")
    def test_github_request_handles_forbidden_status(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(403, {"message": "Forbidden"}),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        with self.assertRaises(Exception) as ctx:
            source.list_repositories()
        self.assertIn("Authentication failed", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_pagination_handles_empty_values(self, session_cls):
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
    def test_github_handles_invalid_json_response(self, session_cls):
        import json

        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, json.JSONDecodeError("invalid", "", 0)),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        with self.assertRaises(Exception) as ctx:
            source.list_repositories()
        self.assertIn("Invalid JSON", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_pagination_stops_when_no_next_page(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [{"path_with_namespace": "acme/one"}],
                headers={"X-Next-Page": "2"},
            ),
            _FakeResponse(
                200,
                [{"path_with_namespace": "acme/two"}],
                headers={},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual(2, len(repositories))
        self.assertEqual(3, session.get.call_count)

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_get_repository_handles_404(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(404, {"error": {"message": "Not found"}}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        with self.assertRaises(Exception) as ctx:
            source.get_repository("acme", "nonexistent")
        self.assertIn("failed with status 404", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_github_repository_without_ssh_url(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(
                200,
                {
                    "full_name": "acme/service",
                    "clone_url": "https://github.com/acme/service.git",
                    "archived": False,
                },
            ),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repository = source.get_repository("acme", "service")

        clone_links = repository["links"]["clone"]
        self.assertEqual(1, len(clone_links))
        self.assertEqual("https", clone_links[0]["name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_gitlab_handles_invalid_pagination_header(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                [{"path_with_namespace": "acme/one"}],
                headers={"X-Next-Page": "not-a-number"},
            ),
        ]
        session_cls.return_value = session

        source = GitLabSource("user", "token")
        with self.assertRaises(Exception) as ctx:
            source.list_repositories()
        self.assertIn("Invalid pagination header", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_list_branches_handles_empty_repository(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": []}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.list_branches("acme/empty-repo")

        self.assertEqual(0, len(branches))


if __name__ == "__main__":
    unittest.main()