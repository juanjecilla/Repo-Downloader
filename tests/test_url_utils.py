import unittest

from utils.url_utils import get_ssh_url_from_list


class TestUrlUtils(unittest.TestCase):
    def test_get_ssh_url_from_list_returns_matching_url(self):
        url = get_ssh_url_from_list(
            [
                {"name": "https", "href": "https://example.com/repo.git"},
                {"name": "ssh", "href": "git@example.com:repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)

    def test_get_ssh_url_from_list_returns_none_for_empty_input(self):
        self.assertIsNone(get_ssh_url_from_list([]))

    def test_get_ssh_url_from_list_returns_none_when_ssh_missing(self):
        url = get_ssh_url_from_list([{"name": "https", "href": "https://example.com/repo.git"}])
        self.assertIsNone(url)

    def test_get_ssh_url_from_list_returns_first_ssh_match(self):
        url = get_ssh_url_from_list(
            [
                {"name": "ssh", "href": "git@first.com:repo.git"},
                {"name": "ssh", "href": "git@second.com:repo.git"},
            ]
        )
        self.assertEqual("git@first.com:repo.git", url)

    def test_get_ssh_url_from_list_handles_missing_name_key(self):
        url = get_ssh_url_from_list(
            [
                {"href": "https://example.com/repo.git"},
                {"name": "ssh", "href": "git@example.com:repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)

    def test_get_ssh_url_from_list_handles_none_values(self):
        url = get_ssh_url_from_list(
            [
                {"name": None, "href": "https://example.com/repo.git"},
                {"name": "ssh", "href": "git@example.com:repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)

    def test_get_ssh_url_from_list_returns_none_for_none_input(self):
        url = get_ssh_url_from_list(None)
        self.assertIsNone(url)

    def test_get_ssh_url_from_list_case_sensitive_match(self):
        # Should only match lowercase "ssh", not "SSH"
        url = get_ssh_url_from_list([{"name": "SSH", "href": "git@example.com:repo.git"}])
        self.assertIsNone(url)

    def test_get_ssh_url_from_list_mixed_entries(self):
        url = get_ssh_url_from_list(
            [
                {"name": "https", "href": "https://example.com/repo.git"},
                {"name": "http", "href": "http://example.com/repo.git"},
                {"name": "ssh", "href": "git@example.com:repo.git"},
                {"name": "git", "href": "git://example.com/repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)

    def test_get_ssh_url_from_list_with_empty_href(self):
        url = get_ssh_url_from_list(
            [
                {"name": "ssh", "href": ""},
            ]
        )
        self.assertEqual("", url)

    def test_get_ssh_url_from_list_with_various_ssh_url_formats(self):
        # Test different valid SSH URL formats
        test_cases = [
            "git@github.com:user/repo.git",
            "ssh://git@gitlab.com/user/repo.git",
            "git@bitbucket.org:workspace/repo.git",
            "ssh://git@example.com:2222/repo.git",
        ]
        for ssh_url in test_cases:
            with self.subTest(ssh_url=ssh_url):
                url = get_ssh_url_from_list([{"name": "ssh", "href": ssh_url}])
                self.assertEqual(ssh_url, url)

    def test_get_ssh_url_from_list_handles_list_with_one_valid_dict(self):
        # Verify it can still find SSH URL when mixed with other types
        url = get_ssh_url_from_list(
            [
                {"name": "https", "href": "https://example.com/repo.git"},
                {"name": "ssh", "href": "git@example.com:repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)


if __name__ == "__main__":
    unittest.main()