import importlib.util
import unittest
from unittest.mock import Mock, patch

from utils.errors import ProviderNotImplementedError


REQUESTS_AVAILABLE = importlib.util.find_spec("requests") is not None
if REQUESTS_AVAILABLE:
    from data.source.remote_sources import BitbucketSource, GitHubSource, GitLabSource
else:
    BitbucketSource = None
    GitHubSource = None
    GitLabSource = None


class _FakeResponse:
    def __init__(self, status_code, payload, links=None):
        self.status_code = status_code
        self._payload = payload
        self.links = links or {}

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
class TestProviderStubs(unittest.TestCase):

    def test_gitlab_stub_is_not_implemented(self):
        provider = GitLabSource("user", "token")
        self.assertFalse(provider.auth_ok())
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_user_info()

    def test_gitlab_stub_list_repositories_raises_not_implemented(self):
        provider = GitLabSource("user", "token")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_repositories()

    def test_gitlab_stub_get_repository_raises_not_implemented(self):
        provider = GitLabSource("user", "token")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_repository("workspace", "repo")

    def test_gitlab_stub_list_branches_raises_not_implemented(self):
        provider = GitLabSource("user", "token")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_branches("workspace/repo")

    def test_gitlab_stub_auth_error_message(self):
        provider = GitLabSource("user", "token")
        self.assertIn("gitlab", provider.auth_error.lower())
        self.assertIn("not implemented", provider.auth_error.lower())


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestBitbucketSourceEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_error_on_request_exception(self, session_cls):
        import requests
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            requests.RequestException("network error"),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        with self.assertRaises(Exception) as context:
            source._request_json("https://api.bitbucket.org/2.0/test")

        self.assertIn("network error", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_error_on_403_forbidden(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(403, {"error": "forbidden"}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        with self.assertRaises(Exception) as context:
            source._request_json("https://api.bitbucket.org/2.0/test")

        self.assertIn("Authentication failed", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_error_on_500_server_error(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(500, {"error": "server error"}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        with self.assertRaises(Exception) as context:
            source._request_json("https://api.bitbucket.org/2.0/test")

        self.assertIn("failed with status 500", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_error_on_invalid_json(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, ValueError("invalid json")),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        with self.assertRaises(Exception) as context:
            source._request_json("https://api.bitbucket.org/2.0/test")

        self.assertIn("Invalid JSON", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_paginated_results_raises_error_on_missing_values(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"invalid": "no values key"}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        with self.assertRaises(Exception) as context:
            source._get_paginated_results("https://api.bitbucket.org/2.0/test")

        self.assertIn("did not include 'values'", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_legacy_get_repo_list_alias(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/one"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repositories = source.get_repo_list()

        self.assertEqual(1, len(repositories))
        self.assertEqual("acme/one", repositories[0]["repository"]["full_name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_legacy_get_repositories_by_permission_alias(self, session_cls):
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
    def test_bitbucket_legacy_get_branches_alias(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"name": "main"}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.get_branches("acme/repo")

        self.assertEqual(1, len(branches))
        self.assertEqual("main", branches[0]["name"])


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestGitHubSourceEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_request_raises_error_on_request_exception(self, session_cls):
        import requests
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            requests.RequestException("network error"),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        with self.assertRaises(Exception) as context:
            source._request("https://api.github.com/test")

        self.assertIn("network error", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_error_on_invalid_json(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, ValueError("invalid json")),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        with self.assertRaises(Exception) as context:
            source._request_json("https://api.github.com/test")

        self.assertIn("Invalid JSON", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_paginated_results_raises_error_on_non_list_payload(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(200, {"not": "a list"}),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        with self.assertRaises(Exception) as context:
            source._get_paginated_results("https://api.github.com/test")

        self.assertIn("returned a non-list payload", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_normalize_repository_adds_missing_links(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(200, {"login": "tester"})]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repository = {
            "full_name": "acme/service",
            "ssh_url": "git@github.com:acme/service.git",
            "clone_url": "https://github.com/acme/service.git",
        }
        normalized = source._normalize_repository_payload(repository)

        self.assertIn("links", normalized)
        self.assertIn("clone", normalized["links"])
        self.assertEqual(2, len(normalized["links"]["clone"]))

    @patch("data.source.remote_sources.requests.Session")
    def test_normalize_repository_preserves_existing_links(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(200, {"login": "tester"})]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repository = {
            "full_name": "acme/service",
            "ssh_url": "git@github.com:acme/service.git",
            "clone_url": "https://github.com/acme/service.git",
            "links": {"html": {"href": "https://github.com/acme/service"}},
        }
        normalized = source._normalize_repository_payload(repository)

        self.assertIn("html", normalized["links"])
        self.assertIn("clone", normalized["links"])

    @patch("data.source.remote_sources.requests.Session")
    def test_normalize_repository_handles_missing_urls(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(200, {"login": "tester"})]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repository = {"full_name": "acme/service"}
        normalized = source._normalize_repository_payload(repository)

        self.assertIn("links", normalized)
        self.assertEqual([], normalized["links"]["clone"])

    @patch("data.source.remote_sources.requests.Session")
    def test_list_repositories_without_workspace(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"login": "tester"}),
            _FakeResponse(
                200,
                [{"full_name": "user/repo1"}, {"full_name": "org/repo2"}],
            ),
        ]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        repositories = source.list_repositories()

        self.assertEqual(2, len(repositories))
        requested_url = session.get.call_args_list[1].args[0]
        self.assertIn("/user/repos", requested_url)

    @patch("data.source.remote_sources.requests.Session")
    def test_github_current_user_property(self, session_cls):
        session = Mock()
        session.get.side_effect = [_FakeResponse(200, {"login": "tester", "id": 123})]
        session_cls.return_value = session

        source = GitHubSource("user", "token")
        self.assertEqual("tester", source.current_user["login"])
        self.assertEqual(123, source.current_user["id"])


if __name__ == "__main__":
    unittest.main()