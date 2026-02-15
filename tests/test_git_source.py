import importlib.util
import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from utils.errors import RepositorySyncError


GITPYTHON_AVAILABLE = importlib.util.find_spec("git") is not None


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def setUp(self):
        from data.source.git_source import GitSource

        self.GitSource = GitSource

    def test_init_expands_tilde_in_key_path(self):
        with patch("os.path.expanduser", return_value="/home/user/.ssh/id_rsa") as mock_expand:
            source = self.GitSource(key_path="~/.ssh/id_rsa")
            mock_expand.assert_called_once_with("~/.ssh/id_rsa")
            self.assertEqual("/home/user/.ssh/id_rsa", source._key_path)

    def test_build_git_env_quotes_ssh_key_path(self):
        source = self.GitSource(key_path="/home/user/.ssh/key with spaces")
        env = source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("'/home/user/.ssh/key with spaces'", env["GIT_SSH_COMMAND"])
        self.assertIn("-o StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_mirror_mode(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo
        source = self.GitSource()

        result = source.clone_repo("git@example.com:repo.git", "/path/mirror.git", mirror=True)

        self.assertEqual(mock_repo, result)
        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/path/mirror.git", call_args[0][1])
        self.assertTrue(call_args[1]["mirror"])
        self.assertIn("env", call_args[1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_working_mode(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo
        source = self.GitSource()

        result = source.clone_repo("git@example.com:repo.git", "/path/working", mirror=False)

        self.assertEqual(mock_repo, result)
        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/path/working", call_args[0][1])
        self.assertNotIn("mirror", call_args[1])
        self.assertIn("env", call_args[1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_failure(self, mock_repo_class):
        from git.exc import GitCommandError

        mock_repo_class.clone_from.side_effect = GitCommandError("git clone", 128)
        source = self.GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            source.clone_repo("git@example.com:repo.git", "/path/mirror.git", mirror=True)

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_instance(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        source = self.GitSource()

        result = source.open_repo("/path/to/repo")

        self.assertEqual(mock_repo, result)
        mock_repo_class.assert_called_once_with("/path/to/repo")

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_on_invalid_git_repository(self, mock_repo_class):
        from git.exc import InvalidGitRepositoryError

        mock_repo_class.side_effect = InvalidGitRepositoryError("/path/invalid")
        source = self.GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/path/invalid")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/path/invalid", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_on_no_such_path(self, mock_repo_class):
        from git.exc import NoSuchPathError

        mock_repo_class.side_effect = NoSuchPathError("/nonexistent")
        source = self.GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/nonexistent")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_runs_remote_update_prune(self, mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo
        source = self.GitSource()

        result = source.update_mirror("/path/mirror.git")

        self.assertEqual(mock_repo, result)
        mock_git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_on_git_command_error(self, mock_repo_class):
        from git.exc import GitCommandError

        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("git remote update", 1)
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo
        source = self.GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            source.update_mirror("/path/mirror.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/path/mirror.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_fetches_origin_with_prune_tags(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        source = self.GitSource()

        result = source.fetch_working_copy("/path/working")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_on_git_command_error(self, mock_repo_class):
        from git.exc import GitCommandError

        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("git fetch", 1)
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        source = self.GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            source.fetch_working_copy("/path/working")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/path/working", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_uses_existing_local_branch(self, _mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo.heads = ["main", "dev"]
        source = self.GitSource()

        source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_tracking_branch_if_not_exists(self, _mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo.heads = ["main"]
        source = self.GitSource()

        source.checkout_branch(mock_repo, "dev")

        mock_git.checkout.assert_called_once_with("-B", "dev", "origin/dev")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_on_git_command_error(self, _mock_repo_class):
        from git.exc import GitCommandError

        mock_repo = Mock()
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError("git checkout", 1)
        mock_repo.git = mock_git
        mock_repo.heads = []
        source = self.GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            source.checkout_branch(mock_repo, "feature/new")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("feature/new", str(context.exception))

    def test_build_git_env_uses_provided_key_path(self):
        custom_key = "/custom/path/to/key"
        source = self.GitSource(key_path=custom_key)
        env = source._build_git_env()

        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn(f"'{custom_key}'", env["GIT_SSH_COMMAND"])


if __name__ == "__main__":
    unittest.main()