import os
import unittest
from unittest.mock import MagicMock, patch

try:
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
    from data.source.git_source import GitSource
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    GitSource = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    GITPYTHON_AVAILABLE = False

from utils.errors import RepositorySyncError


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_initialization_with_default_key_path(self):
        git_source = GitSource()
        self.assertTrue(git_source._key_path.endswith("id_rsa"))

    def test_initialization_with_custom_key_path(self):
        git_source = GitSource(key_path="/custom/path/key")
        self.assertEqual("/custom/path/key", git_source._key_path)

    def test_initialization_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        self.assertFalse(git_source._key_path.startswith("~"))
        self.assertTrue(os.path.isabs(git_source._key_path))

    def test_build_git_env_includes_ssh_command(self):
        git_source = GitSource(key_path="/test/key")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path with spaces/key")
        env = git_source._build_git_env()
        self.assertIn("'/path with spaces/key'", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_mirror_passes_mirror_flag(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo_cls.clone_from.return_value = mock_repo

        result = git_source.clone_repo("git@example.com:repo.git", "/tmp/repo.git", mirror=True)

        mock_repo_cls.clone_from.assert_called_once()
        call_args = mock_repo_cls.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/tmp/repo.git", call_args[0][1])
        self.assertTrue(call_args[1]["mirror"])
        self.assertIn("env", call_args[1])
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_working_does_not_pass_mirror_flag(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo_cls.clone_from.return_value = mock_repo

        result = git_source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)

        mock_repo_cls.clone_from.assert_called_once()
        call_args = mock_repo_cls.clone_from.call_args
        self.assertNotIn("mirror", call_args[1])
        self.assertIn("env", call_args[1])
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_failure(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo_cls.clone_from.side_effect = GitCommandError("clone", "failed")

        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo.git", mirror=True)

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_object(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        result = git_source.open_repo("/tmp/repo")

        mock_repo_cls.assert_called_once_with("/tmp/repo")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_on_invalid_repository(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo_cls.side_effect = InvalidGitRepositoryError()

        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/invalid/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/invalid/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_on_no_such_path(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo_cls.side_effect = NoSuchPathError()

        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/nonexistent/path")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_git_remote_update_prune(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        result = git_source.update_mirror("/tmp/repo.git")

        mock_repo.git.remote.assert_called_once_with("update", "--prune")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_sync_error_on_failure(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", "update failed")
        mock_repo_cls.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/tmp/repo.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/tmp/repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_origin = MagicMock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_cls.return_value = mock_repo

        result = git_source.fetch_working_copy("/tmp/repo")

        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_sync_error_on_failure(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_origin = MagicMock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "network error")
        mock_repo.remotes.origin = mock_origin
        mock_repo_cls.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/tmp/repo")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/tmp/repo", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_existing_local_branch(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo.heads = ["main", "dev"]

        git_source.checkout_branch(mock_repo, "main")

        mock_repo.git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_from_remote_tracking(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo.heads = []

        git_source.checkout_branch(mock_repo, "feature-branch")

        mock_repo.git.checkout.assert_called_once_with("-B", "feature-branch", "origin/feature-branch")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_sync_error_on_failure(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", "branch not found")

        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "missing-branch")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("missing-branch", str(context.exception))


if __name__ == "__main__":
    unittest.main()