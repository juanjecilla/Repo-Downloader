import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from utils.errors import RepositorySyncError

try:
    from data.source.git_source import GitSource
    GIT_AVAILABLE = True
except ModuleNotFoundError:
    GitSource = None
    GIT_AVAILABLE = False


@unittest.skipUnless(GIT_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def setUp(self):
        self.GitSource = GitSource

    def test_build_git_env_includes_ssh_command(self):
        git_source = self.GitSource(key_path="~/.ssh/custom_key")
        env = git_source._build_git_env()

        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_expands_tilde_in_key_path(self):
        git_source = self.GitSource(key_path="~/.ssh/id_rsa")
        env = git_source._build_git_env()

        self.assertNotIn("~", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path_for_shell_safety(self):
        git_source = self.GitSource(key_path="/path/with spaces/key")
        env = git_source._build_git_env()

        self.assertIn("GIT_SSH_COMMAND", env)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_without_mirror(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = self.GitSource()
        result = git_source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        self.assertEqual(mock_repo, result)
        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/local/path", call_args[0][1])
        self.assertIn("env", call_args[1])
        self.assertNotIn("mirror", call_args[1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_mirror(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = self.GitSource()
        result = git_source.clone_repo("git@example.com:repo.git", "/local/path", mirror=True)

        self.assertEqual(mock_repo, result)
        call_args = mock_repo_class.clone_from.call_args
        self.assertTrue(call_args[1].get("mirror"))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_failure(self, mock_repo_class):
        from git.exc import GitCommandError
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", "failed")

        git_source = self.GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:repo.git", "/local/path")

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_instance(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        git_source = self.GitSource()
        result = git_source.open_repo("/local/repo")

        self.assertEqual(mock_repo, result)
        mock_repo_class.assert_called_once_with("/local/repo")

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_on_invalid_repository(self, mock_repo_class):
        from git.exc import InvalidGitRepositoryError
        mock_repo_class.side_effect = InvalidGitRepositoryError("/not/a/repo")

        git_source = self.GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/not/a/repo")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_on_missing_path(self, mock_repo_class):
        from git.exc import NoSuchPathError
        mock_repo_class.side_effect = NoSuchPathError("/missing/path")

        git_source = self.GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/missing/path")

        self.assertIn("Invalid local repository path", str(context.exception))

    def test_update_mirror_calls_git_remote_update(self):
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git

        with patch.object(self.GitSource, "open_repo", return_value=mock_repo):
            git_source = self.GitSource()
            result = git_source.update_mirror("/local/mirror.git")

        self.assertEqual(mock_repo, result)
        mock_git.remote.assert_called_once_with("update", "--prune")

    def test_update_mirror_raises_on_git_failure(self):
        from git.exc import GitCommandError
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("remote", "update failed")
        mock_repo.git = mock_git

        with patch.object(self.GitSource, "open_repo", return_value=mock_repo):
            git_source = self.GitSource()
            with self.assertRaises(RepositorySyncError) as context:
                git_source.update_mirror("/local/mirror.git")

        self.assertIn("Failed updating mirror", str(context.exception))

    def test_fetch_working_copy_calls_origin_fetch(self):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin

        with patch.object(self.GitSource, "open_repo", return_value=mock_repo):
            git_source = self.GitSource()
            result = git_source.fetch_working_copy("/local/working")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    def test_fetch_working_copy_raises_on_git_failure(self):
        from git.exc import GitCommandError
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "fetch failed")
        mock_repo.remotes.origin = mock_origin

        with patch.object(self.GitSource, "open_repo", return_value=mock_repo):
            git_source = self.GitSource()
            with self.assertRaises(RepositorySyncError) as context:
                git_source.fetch_working_copy("/local/working")

        self.assertIn("Failed fetching working repository", str(context.exception))

    def test_checkout_branch_existing_local_branch(self):
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev"]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = self.GitSource()
        git_source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    def test_checkout_branch_creates_tracking_branch(self):
        mock_repo = Mock()
        mock_repo.heads = ["main"]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = self.GitSource()
        git_source.checkout_branch(mock_repo, "feature")

        mock_git.checkout.assert_called_once_with("-B", "feature", "origin/feature")

    def test_checkout_branch_raises_on_git_failure(self):
        from git.exc import GitCommandError
        mock_repo = Mock()
        mock_repo.heads = []
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError("checkout", "branch not found")
        mock_repo.git = mock_git

        git_source = self.GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "nonexistent")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("nonexistent", str(context.exception))


if __name__ == "__main__":
    unittest.main()