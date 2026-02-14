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


if __name__ == "__main__":
    unittest.main()
