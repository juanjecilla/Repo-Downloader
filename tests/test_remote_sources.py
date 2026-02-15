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
    def test_request_json_raises_remote_api_error_on_request_exception(self, session_cls):
        from utils.errors import RemoteAPIError

        session = Mock()
        session.get.return_value = _FakeResponse(200, {"username": "tester"})
        session_cls.return_value = session

        source = BitbucketSource("user", "token")

        # Now configure session to raise exception for subsequent calls
        import requests
        session.get.side_effect = requests.RequestException("connection timeout")

        with self.assertRaises(RemoteAPIError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("Request to", str(context.exception))
        self.assertIn("failed", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_auth_error_on_401(self, session_cls):
        session = Mock()
        session.get.return_value = _FakeResponse(401, {})
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import AuthenticationError

        with self.assertRaises(AuthenticationError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("Authentication failed", str(context.exception))
        self.assertIn("401", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_auth_error_on_403(self, session_cls):
        session = Mock()
        session.get.return_value = _FakeResponse(403, {})
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import AuthenticationError

        with self.assertRaises(AuthenticationError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("403", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_remote_api_error_on_4xx(self, session_cls):
        session = Mock()
        session.get.return_value = _FakeResponse(404, {})
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError

        with self.assertRaises(RemoteAPIError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("404", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_remote_api_error_on_5xx(self, session_cls):
        session = Mock()
        session.get.return_value = _FakeResponse(500, {})
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError

        with self.assertRaises(RemoteAPIError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("500", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_request_json_raises_remote_api_error_on_invalid_json(self, session_cls):
        session = Mock()
        response = _FakeResponse(200, ValueError("invalid json"))
        session.get.return_value = response
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError

        with self.assertRaises(RemoteAPIError) as context:
            source._request_json("https://api.bitbucket.org/test")
        self.assertIn("Invalid JSON", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_get_paginated_results_raises_error_when_values_missing(self, session_cls):
        session = Mock()
        session.get.return_value = _FakeResponse(200, {"no_values_key": []})
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        from utils.errors import RemoteAPIError

        with self.assertRaises(RemoteAPIError) as context:
            source._get_paginated_results("https://api.bitbucket.org/test")
        self.assertIn("did not include 'values'", str(context.exception))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_configures_retry_adapter(self, session_cls):
        session = Mock()
        session_cls.return_value = session

        # Trigger auth by making it succeed
        session.get.return_value = _FakeResponse(200, {"username": "test"})
        BitbucketSource("user", "token", timeout=10, retries=5)

        # Verify mount was called to set up retry adapter
        session.mount.assert_called()
        mount_call = session.mount.call_args
        self.assertEqual("https://", mount_call[0][0])

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_current_user_property(self, session_cls):
        session = Mock()
        session.get.return_value = _FakeResponse(200, {"username": "testuser", "uuid": "123"})
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        self.assertEqual("testuser", source.current_user["username"])

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_list_repositories_filters_by_workspace(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(
                200,
                {
                    "values": [
                        {"repository": {"full_name": "workspace1/repo1"}},
                        {"repository": {"full_name": "workspace2/repo2"}},
                        {"repository": {"full_name": "workspace1/repo3"}},
                    ]
                },
            ),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repos = source.list_repositories(workspace="workspace1")
        self.assertEqual(2, len(repos))
        self.assertTrue(all("workspace1" in r["repository"]["full_name"] for r in repos))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_get_repository_makes_correct_api_call(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"full_name": "workspace/repo", "is_private": True}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repo = source.get_repository("workspace", "repo")

        self.assertEqual("workspace/repo", repo["full_name"])
        # Verify the correct URL was called
        calls = [call[0][0] for call in session.get.call_args_list]
        self.assertTrue(
            any("repositories/workspace/repo" in call for call in calls),
            f"Expected repository API call in {calls}",
        )

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_list_branches_makes_correct_api_call(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"name": "main"}, {"name": "dev"}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.list_branches("workspace/repo")

        self.assertEqual(2, len(branches))
        self.assertEqual("main", branches[0]["name"])

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_legacy_get_repo_list_method(self, session_cls):
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
    def test_bitbucket_source_legacy_get_repositories_by_permission_method(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/repo"}}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        repos = source.get_repositories_by_permission(role="owner")

        self.assertEqual(1, len(repos))

    @patch("data.source.remote_sources.requests.Session")
    def test_bitbucket_source_legacy_get_branches_method(self, session_cls):
        session = Mock()
        session.get.side_effect = [
            _FakeResponse(200, {"username": "tester"}),
            _FakeResponse(200, {"values": [{"name": "main"}]}),
        ]
        session_cls.return_value = session

        source = BitbucketSource("user", "token")
        branches = source.get_branches("workspace/repo")

        self.assertEqual(1, len(branches))

    def test_not_implemented_provider_raises_on_get_user_info(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("custom-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_user_info()

    def test_not_implemented_provider_raises_on_list_repositories(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("custom-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_repositories()

    def test_not_implemented_provider_raises_on_get_repository(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("custom-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.get_repository("workspace", "repo")

    def test_not_implemented_provider_raises_on_list_branches(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("custom-provider")
        with self.assertRaises(ProviderNotImplementedError):
            provider.list_branches("workspace/repo")

    def test_not_implemented_provider_auth_ok_returns_false(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("custom-provider")
        self.assertFalse(provider.auth_ok())

    def test_not_implemented_provider_has_auth_error(self):
        from data.source.remote_sources import _NotImplementedProvider

        provider = _NotImplementedProvider("custom-provider")
        self.assertIn("not implemented", provider.auth_error.lower())
        self.assertIn("custom-provider", provider.auth_error)


if __name__ == "__main__":
    unittest.main()