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

    def test_get_ssh_url_from_list_returns_first_ssh_when_multiple_present(self):
        url = get_ssh_url_from_list(
            [
                {"name": "ssh", "href": "git@example.com:repo.git"},
                {"name": "https", "href": "https://example.com/repo.git"},
                {"name": "ssh", "href": "ssh://git@example.com/repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)

    def test_get_ssh_url_from_list_handles_none_input(self):
        url = get_ssh_url_from_list(None)
        self.assertIsNone(url)

    def test_get_ssh_url_from_list_handles_malformed_entries(self):
        url = get_ssh_url_from_list(
            [
                {"href": "https://example.com/repo.git"},
                {"name": "ssh", "href": "git@example.com:repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)

    def test_get_ssh_url_from_list_raises_key_error_for_entry_without_href(self):
        with self.assertRaises(KeyError):
            get_ssh_url_from_list(
                [
                    {"name": "ssh"},
                    {"name": "https", "href": "https://example.com/repo.git"},
                ]
            )

    def test_get_ssh_url_from_list_returns_ssh_url_at_any_position(self):
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