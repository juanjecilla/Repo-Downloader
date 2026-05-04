import importlib.util
import unittest
from unittest.mock import Mock, patch

from data.source.provider_interface import RemoteProvider
from utils.errors import RemoteAPIError

REQUESTS_AVAILABLE = importlib.util.find_spec("requests") is not None


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


@unittest.skipUnless(REQUESTS_AVAILABLE, "requests is required for provider contract tests")
class TestProviderContract(unittest.TestCase):
    def test_provider_classes_implement_contract(self):
        from data.source.remote_sources import (
            BitbucketSource,
            GitHubSource,
            GitLabSource,
        )

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

    @patch("data.source.remote_sources.requests.Session")
    def test_providers_map_auth_failure_consistently(self, session_cls):
        from data.source.remote_sources import (
            BitbucketSource,
            GitHubSource,
            GitLabSource,
        )

        for provider_class in (BitbucketSource, GitHubSource, GitLabSource):
            with self.subTest(provider=provider_class.provider_name):
                session = Mock()
                session.get.side_effect = [_FakeResponse(401, {"error": "auth"})]
                session_cls.return_value = session
                provider = provider_class("user", "bad-token")
                self.assertFalse(provider.auth_ok())
                self.assertIn("Authentication failed", provider.auth_error)

    @patch("data.source.remote_sources.requests.Session")
    def test_providers_support_paginated_repository_listing(self, session_cls):
        from data.source.remote_sources import (
            BitbucketSource,
            GitHubSource,
            GitLabSource,
        )

        provider_cases = (
            {
                "class": BitbucketSource,
                "responses": [
                    _FakeResponse(200, {"username": "tester"}),
                    _FakeResponse(
                        200,
                        {
                            "values": [{"repository": {"full_name": "acme/one"}}],
                            "next": "https://api.bitbucket.org/page-2",
                        },
                    ),
                    _FakeResponse(200, {"values": [{"repository": {"full_name": "acme/two"}}]}),
                ],
                "list_kwargs": {"role": "member"},
            },
            {
                "class": GitHubSource,
                "responses": [
                    _FakeResponse(200, {"login": "tester"}),
                    _FakeResponse(
                        200,
                        [{"full_name": "acme/one"}],
                        links={"next": {"url": "https://api.github.com/user/repos?page=2"}},
                    ),
                    _FakeResponse(200, [{"full_name": "acme/two"}]),
                ],
                "list_kwargs": {},
            },
            {
                "class": GitLabSource,
                "responses": [
                    _FakeResponse(200, {"username": "tester"}),
                    _FakeResponse(
                        200,
                        [
                            {
                                "path_with_namespace": "acme/one",
                                "ssh_url_to_repo": "git@gitlab.com:acme/one.git",
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
                            }
                        ],
                        headers={},
                    ),
                ],
                "list_kwargs": {},
            },
        )

        for case in provider_cases:
            with self.subTest(provider=case["class"].provider_name):
                session = Mock()
                session.get.side_effect = case["responses"]
                session_cls.return_value = session
                provider = case["class"]("user", "token")
                repositories = provider.list_repositories(**case["list_kwargs"])
                self.assertEqual(2, len(repositories))

    @patch("data.source.remote_sources.requests.Session")
    def test_providers_raise_remote_api_error_for_invalid_pagination_payload(self, session_cls):
        from data.source.remote_sources import (
            BitbucketSource,
            GitHubSource,
            GitLabSource,
        )

        provider_cases = (
            {
                "class": BitbucketSource,
                "responses": [
                    _FakeResponse(200, {"username": "tester"}),
                    _FakeResponse(200, {"unexpected": []}),
                ],
                "list_kwargs": {"role": "member"},
            },
            {
                "class": GitHubSource,
                "responses": [
                    _FakeResponse(200, {"login": "tester"}),
                    _FakeResponse(200, {"unexpected": []}),
                ],
                "list_kwargs": {},
            },
            {
                "class": GitLabSource,
                "responses": [
                    _FakeResponse(200, {"username": "tester"}),
                    _FakeResponse(200, {"unexpected": []}),
                ],
                "list_kwargs": {},
            },
        )

        for case in provider_cases:
            with self.subTest(provider=case["class"].provider_name):
                session = Mock()
                session.get.side_effect = case["responses"]
                session_cls.return_value = session
                provider = case["class"]("user", "token")
                with self.assertRaises(RemoteAPIError):
                    provider.list_repositories(**case["list_kwargs"])


if __name__ == "__main__":
    unittest.main()
