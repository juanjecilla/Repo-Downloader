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
class TestBitbucketSourceErrorHandling(unittest.TestCase):
    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_network_error(self, session_cls):
        import requests

        session = Mock()
        session.get.side_effect = requests.RequestException("network failure")
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError

        with self.assertRaises(RemoteAPIError) as ctx:
            source._request_json("https://example.com/test")
        self.assertIn("network failure", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_401_status(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(401, {}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import AuthenticationError

        with self.assertRaises(AuthenticationError) as ctx:
            source._request_json("https://example.com/test")
        self.assertIn("401", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_403_status(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(403, {}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import AuthenticationError

        with self.assertRaises(AuthenticationError) as ctx:
            source._request_json("https://example.com/test")
        self.assertIn("403", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_500_status(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(500, {}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError

        with self.assertRaises(RemoteAPIError) as ctx:
            source._request_json("https://example.com/test")
        self.assertIn("500", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_on_invalid_json(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, ValueError("invalid json")),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError

        with self.assertRaises(RemoteAPIError) as ctx:
            source._request_json("https://example.com/test")
        self.assertIn("Invalid JSON", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_paginated_results_raises_on_missing_values(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"no_values_key": []}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError

        with self.assertRaises(RemoteAPIError) as ctx:
            source._get_paginated_results("https://example.com/test")
        self.assertIn("did not include 'values'", str(ctx.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_user_info_constructs_correct_url(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"username": "tester"}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        user_info = source.get_user_info()

        self.assertEqual("tester", user_info["username"])
        session.get.assert_called()
        call_url = session.get.call_args[0][0]
        self.assertTrue(call_url.endswith("/user/"))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_repository_constructs_correct_url(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"full_name": "acme/repo"}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repo = source.get_repository("acme", "repo")

        self.assertEqual("acme/repo", repo["full_name"])
        call_url = session.get.call_args[0][0]
        self.assertIn("/repositories/acme/repo", call_url)

    @patch("data.source.remote_sources.requests.Session")
    def test_list_branches_constructs_correct_url(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"name": "main"}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.list_branches("acme/repo")

        self.assertEqual([{"name": "main"}], branches)
        call_url = session.get.call_args[0][0]
        self.assertIn("/repositories/acme/repo/refs/branches", call_url)

    @patch("data.source.remote_sources.requests.Session")
    def test_legacy_get_repo_list_delegates_to_list_repositories(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/one"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repos = source.get_repo_list(workspace="acme", paginated=True)

        self.assertEqual(1, len(repos))
        self.assertEqual("acme/one", repos[0]["repository"]["full_name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_legacy_get_repositories_by_permission_delegates(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/one"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repos = source.get_repositories_by_permission(role="contributor")

        self.assertEqual(1, len(repos))

    @patch("data.source.remote_sources.requests.Session")
    def test_legacy_get_branches_delegates_to_list_branches(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"name": "main"}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.get_branches("acme/repo")

        self.assertEqual([{"name": "main"}], branches)


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider tests")
class TestNotImplementedProvider(unittest.TestCase):
    def test_not_implemented_provider_auth_ok_returns_false(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("test-provider")
        self.assertFalse(provider.auth_ok())

    def test_not_implemented_provider_has_auth_error(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("test-provider")
        self.assertIn("not implemented", provider.auth_error)

    def test_not_implemented_provider_raises_on_get_user_info(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("test-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_user_info()

    def test_not_implemented_provider_raises_on_list_repositories(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("test-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_repositories()

    def test_not_implemented_provider_raises_on_get_repository(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("test-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_repository("workspace", "repo")

    def test_not_implemented_provider_raises_on_list_branches(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("test-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_branches("workspace/repo")


if __name__ == "__main__":
    unittest.main()