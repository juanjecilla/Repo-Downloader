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
                {"name": "ssh", "href": "git@example.com:repo1.git"},
                {"name": "ssh", "href": "git@example.com:repo2.git"},
            ]
        )
        self.assertEqual("git@example.com:repo1.git", url)

    def test_get_ssh_url_from_list_skips_entries_without_name(self):
        url = get_ssh_url_from_list(
            [
                {"href": "https://example.com/repo.git"},
                {"name": "ssh", "href": "git@example.com:repo.git"},
            ]
        )
        self.assertEqual("git@example.com:repo.git", url)

    def test_get_ssh_url_from_list_handles_none_input(self):
        self.assertIsNone(get_ssh_url_from_list(None))


if __name__ == "__main__":
    unittest.main()