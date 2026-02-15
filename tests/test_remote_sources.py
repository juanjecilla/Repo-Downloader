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
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

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
class TestProviderStubs(unittest.TestCase):
    def test_github_stub_is_not_implemented(self):
        provider = GitHubSource("user", "token")
        self.assertFalse(provider.auth_ok())
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_repositories()

    def test_gitlab_stub_is_not_implemented(self):
        provider = GitLabSource("user", "token")
        self.assertFalse(provider.auth_ok())
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_user_info()


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestBitbucketSourceEdgeCases(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_network_error(self, session_cls):
        from utils.errors import RemoteAPIError
        import requests

        session = Mock()
        session.get.side_effect = requests.RequestException("Network timeout")
        session_cls.return_value = session

        source = BitbucketSource.__new__(BitbucketSource)
        source._session = session
        source._timeout = 20

        with self.assertRaises(RemoteAPIError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("Request to", str(context.exception))
        self.assertIn("failed", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_invalid_json(self, session_cls):
        from utils.errors import RemoteAPIError

        session = Mock()
        response = _FakeResponse(200, ValueError("Invalid JSON"))
        session.get.return_value = response
        session_cls.return_value = session

        source = BitbucketSource.__new__(BitbucketSource)
        source._session = session
        source._timeout = 20

        with self.assertRaises(RemoteAPIError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("Invalid JSON", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_403_forbidden(self, session_cls):
        from utils.errors import AuthenticationError

        session = Mock()
        session.get.return_value = _FakeResponse(403, {"error": "Forbidden"})
        session_cls.return_value = session

        source = BitbucketSource.__new__(BitbucketSource)
        source._session = session
        source._timeout = 20

        with self.assertRaises(AuthenticationError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("Authentication failed", str(context.exception))
        self.assertIn("403", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_500_server_error(self, session_cls):
        from utils.errors import RemoteAPIError

        session = Mock()
        session.get.return_value = _FakeResponse(500, {"error": "Server error"})
        session_cls.return_value = session

        source = BitbucketSource.__new__(BitbucketSource)
        source._session = session
        source._timeout = 20

        with self.assertRaises(RemoteAPIError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("failed with status 500", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_paginated_results_raises_on_missing_values_key(self, session_cls):
        from utils.errors import RemoteAPIError

        session = Mock()
        session.get.return_value = _FakeResponse(200, {"no_values_key": []})
        session_cls.return_value = session

        source = BitbucketSource.__new__(BitbucketSource)
        source._session = session
        source._timeout = 20

        with self.assertRaises(RemoteAPIError) as context:
            source._get_paginated_results("https://api.bitbucket.org/test")
        self.assertIn("did not include 'values'", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_legacy_get_repo_list_ignores_paginated_argument(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/one"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repos = source.get_repo_list(paginated=True)

        self.assertEqual(1, len(repos))

    @patch("data.source.remote_sources.requests.Session")
    def test_legacy_get_branches_calls_list_branches(self, session_cls):
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

    @patch("data.source.remote_sources.requests.Session")
    def test_current_user_property_returns_cached_user(self, session_cls):
        session = Mock()
        session.get.return_value = _FakeResponse(200, {"username": "tester"})
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        user = source.current_user

        self.assertEqual("tester", user["username"])


if __name__ == "__main__":
    unittest.main()