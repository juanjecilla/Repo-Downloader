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

    def test_get_ssh_url_from_list_returns_first_ssh_when_multiple_exist(self):
        url = get_ssh_url_from_list(
            [
                {"name": "ssh", "href": "git@github.com:acme/repo.git"},
                {"name": "ssh", "href": "git@gitlab.com:acme/repo.git"},
            ]
        )
        self.assertEqual("git@github.com:acme/repo.git", url)

    def test_get_ssh_url_from_list_handles_none_input(self):
        url = get_ssh_url_from_list(None)
        self.assertIsNone(url)

    def test_get_ssh_url_from_list_handles_malformed_dict_without_name(self):
        url = get_ssh_url_from_list([{"href": "git@example.com:repo.git"}])
        self.assertIsNone(url)

    def test_get_ssh_url_from_list_raises_key_error_without_href(self):
        with self.assertRaises(KeyError):
            get_ssh_url_from_list([{"name": "ssh"}])

    def test_get_ssh_url_from_list_ssh_case_sensitive_matching(self):
        url = get_ssh_url_from_list(
            [
                {"name": "SSH", "href": "git@example.com:repo.git"},
                {"name": "https", "href": "https://example.com/repo.git"},
            ]
        )
        self.assertIsNone(url)

    def test_get_ssh_url_from_list_ssh_exact_name_match(self):
        url = get_ssh_url_from_list([{"name": "ssh", "href": "git@example.com:repo.git"}])
        self.assertEqual("git@example.com:repo.git", url)

    def test_get_ssh_url_from_list_ssh_with_custom_port(self):
        url = get_ssh_url_from_list(
            [
                {"name": "https", "href": "https://example.com/repo.git"},
                {"name": "ssh", "href": "ssh://git@example.com:2222/repo.git"},
            ]
        )
        self.assertEqual("ssh://git@example.com:2222/repo.git", url)

    def test_get_ssh_url_from_list_ssh_after_other_protocols(self):
        url = get_ssh_url_from_list(
            [
                {"name": "https", "href": "https://example.com/repo.git"},
                {"name": "http", "href": "http://example.com/repo.git"},
                {"name": "ssh", "href": "git@example.com:repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)


if __name__ == "__main__":
    unittest.main()