import os
import unittest
from unittest.mock import MagicMock, Mock, patch

try:
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
    from data.source.git_source import GitSource
    from utils.errors import RepositorySyncError
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    GitSource = None
    RepositorySyncError = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSource(unittest.TestCase):
    def test_init_expands_tilde_in_key_path(self):
        with patch.dict("os.environ", {"HOME": "/home/testuser"}, clear=False):
            source = GitSource(key_path="~/.ssh/custom_key")
            self.assertEqual("/home/testuser/.ssh/custom_key", source._key_path)

    def test_init_uses_default_key_path(self):
        source = GitSource()
        expanded_path = os.path.expanduser("~/.ssh/id_rsa")
        self.assertEqual(expanded_path, source._key_path)

    def test_build_git_env_returns_ssh_command_with_key(self):
        source = GitSource(key_path="/path/to/key")
        env = source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("/path/to/key", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path_with_spaces(self):
        source = GitSource(key_path="/path with spaces/key")
        env = source._build_git_env()
        # shlex.quote should handle spaces properly
        self.assertIn("GIT_SSH_COMMAND", env)
        ssh_command = env["GIT_SSH_COMMAND"]
        # The path should be quoted or escaped
        self.assertTrue(
            "'/path with spaces/key'" in ssh_command or
            '"/path with spaces/key"' in ssh_command or
            "/path\\ with\\ spaces/key" in ssh_command
        )

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_with_mirror(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        source = GitSource(key_path="/test/key")
        result = source.clone_repo("git@example.com:repo.git", "/local/path", mirror=True)

        mock_repo_class.clone_from.assert_called_once_with(
            "git@example.com:repo.git",
            "/local/path",
            env=unittest.mock.ANY,
            mirror=True,
        )
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_without_mirror(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        source = GitSource()
        result = source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        mock_repo_class.clone_from.assert_called_once()
        call_kwargs = mock_repo_class.clone_from.call_args[1]
        self.assertIn("env", call_kwargs)
        self.assertNotIn("mirror", call_kwargs)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_error(self, mock_repo_class):
        mock_repo_class.clone_from.side_effect = GitCommandError(
            "git clone", 128, stderr="Permission denied"
        )

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.clone_repo("git@example.com:repo.git", "/local/path")

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_object(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        result = source.open_repo("/local/repo")

        mock_repo_class.assert_called_once_with("/local/repo")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_on_invalid_repo(self, mock_repo_class):
        mock_repo_class.side_effect = InvalidGitRepositoryError("/bad/path")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/bad/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/bad/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_on_no_such_path(self, mock_repo_class):
        mock_repo_class.side_effect = NoSuchPathError("/nonexistent")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/nonexistent")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_git_remote_update(self, mock_repo_class):
        mock_repo = MagicMock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        result = source.update_mirror("/mirror/repo.git")

        mock_repo.git.remote.assert_called_once_with("update", "--prune")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_sync_error_on_failure(self, mock_repo_class):
        mock_repo = MagicMock()
        mock_repo.git.remote.side_effect = GitCommandError(
            "git remote update", 1, stderr="Network error"
        )
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.update_mirror("/mirror/repo.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/mirror/repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch(self, mock_repo_class):
        mock_repo = MagicMock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        result = source.fetch_working_copy("/working/repo")

        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_sync_error_on_failure(self, mock_repo_class):
        mock_repo = MagicMock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError(
            "git fetch", 1, stderr="Connection timeout"
        )
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.fetch_working_copy("/working/repo")

        self.assertIn("Failed fetching working repository", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_existing_branch(self, _mock_repo_class):
        mock_repo = MagicMock()
        mock_repo.heads = ["main", "dev"]
        mock_repo.git = Mock()

        source = GitSource()
        source.checkout_branch(mock_repo, "main")

        mock_repo.git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_new_tracking_branch(self, _mock_repo_class):
        mock_repo = MagicMock()
        mock_repo.heads = []
        mock_repo.git = Mock()

        source = GitSource()
        source.checkout_branch(mock_repo, "feature/new")

        mock_repo.git.checkout.assert_called_once_with(
            "-B", "feature/new", "origin/feature/new"
        )

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_sync_error_on_failure(self, _mock_repo_class):
        mock_repo = MagicMock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = GitCommandError(
            "git checkout", 1, stderr="Branch not found"
        )

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.checkout_branch(mock_repo, "nonexistent")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("nonexistent", str(context.exception))

    def test_env_includes_ssh_options(self):
        source = GitSource(key_path="/custom/key")
        env = source._build_git_env()
        ssh_command = env["GIT_SSH_COMMAND"]
        self.assertIn("-i", ssh_command)
        self.assertIn("-o", ssh_command)


if __name__ == "__main__":
    unittest.main()