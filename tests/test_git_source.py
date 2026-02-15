import os
import unittest
from unittest.mock import Mock, patch, MagicMock

from utils.errors import RepositorySyncError

try:
    from git import Repo
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
    from data.source.git_source import GitSource
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    Repo = None
    GitSource = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_init_expands_ssh_key_path_with_tilde(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        self.assertNotIn("~", git_source._key_path)
        self.assertTrue(git_source._key_path.endswith(".ssh/custom_key"))

    def test_init_default_key_path(self):
        git_source = GitSource()
        self.assertTrue(git_source._key_path.endswith(".ssh/id_rsa"))

    def test_build_git_env_includes_ssh_command(self):
        git_source = GitSource(key_path="/path/to/key")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path with spaces/key")
        env = git_source._build_git_env()
        self.assertIn("'/path with spaces/key'", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_mirror_mode(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource(key_path="/test/key")
        result = git_source.clone_repo(
            "git@example.com:repo.git",
            "/local/mirror.git",
            mirror=True
        )

        self.assertEqual(mock_repo, result)
        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/local/mirror.git", call_args[0][1])
        self.assertTrue(call_args[1]["mirror"])
        self.assertIn("env", call_args[1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_working_mode(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource(key_path="/test/key")
        result = git_source.clone_repo(
            "git@example.com:repo.git",
            "/local/working",
            mirror=False
        )

        self.assertEqual(mock_repo, result)
        call_args = mock_repo_class.clone_from.call_args
        self.assertNotIn("mirror", call_args[1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_failure(self, mock_repo_class):
        mock_repo_class.clone_from.side_effect = GitCommandError(
            "git clone",
            128,
            stderr="fatal: repository not found"
        )

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:missing.git", "/local/path")

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:missing.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_object(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.open_repo("/path/to/repo")

        self.assertEqual(mock_repo, result)
        mock_repo_class.assert_called_once_with("/path/to/repo")

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_error_for_invalid_repository(self, mock_repo_class):
        mock_repo_class.side_effect = InvalidGitRepositoryError("/invalid/path")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/invalid/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/invalid/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_error_for_missing_path(self, mock_repo_class):
        mock_repo_class.side_effect = NoSuchPathError("/missing/path")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/missing/path")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_remote_update_prune(self, mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.update_mirror("/mirror/path")

        self.assertEqual(mock_repo, result)
        mock_git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_error_on_git_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("git remote", 1, stderr="error")
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/mirror/path")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/mirror/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_fetches_origin_with_prune_and_tags(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.fetch_working_copy("/working/path")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_error_on_git_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("git fetch", 1, stderr="error")
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/working/path")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/working/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_existing_local_branch(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev"]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_tracking_branch_for_remote(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main"]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "feature/new")

        mock_git.checkout.assert_called_once_with("-B", "feature/new", "origin/feature/new")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_error_on_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = []
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError("git checkout", 1, stderr="error")
        mock_repo.git = mock_git

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "nonexistent")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("nonexistent", str(context.exception))


class TestGitSourceEdgeCases(unittest.TestCase):
    @unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required")
    def test_git_source_with_empty_key_path(self):
        git_source = GitSource(key_path="")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        # Empty path should still be quoted
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])

    @unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required")
    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_special_characters_in_url(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource()
        special_url = "git@example.com:user/repo-name_123.git"
        result = git_source.clone_repo(special_url, "/local/path", mirror=False)

        self.assertEqual(mock_repo, result)
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual(special_url, call_args[0][0])

    @unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required")
    @patch("data.source.git_source.Repo")
    def test_checkout_branch_with_slash_in_name(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = []
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "feature/FR-1234/implementation")

        mock_git.checkout.assert_called_once_with(
            "-B", "feature/FR-1234/implementation", "origin/feature/FR-1234/implementation"
        )


if __name__ == "__main__":
    unittest.main()