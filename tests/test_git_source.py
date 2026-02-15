import importlib.util
import os
import shlex
import unittest
from unittest.mock import Mock, patch

from utils.errors import RepositorySyncError


GITPYTHON_AVAILABLE = importlib.util.find_spec("git") is not None
if GITPYTHON_AVAILABLE:
    from data.source.git_source import GitSource
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
else:
    GitSource = None


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_init_expands_key_path(self):
        git_source = GitSource(key_path="~/custom/.ssh/id_rsa")
        self.assertEqual(os.path.expanduser("~/custom/.ssh/id_rsa"), git_source._key_path)

    def test_init_uses_default_key_path(self):
        git_source = GitSource()
        self.assertEqual(os.path.expanduser("~/.ssh/id_rsa"), git_source._key_path)

    def test_build_git_env_escapes_key_path(self):
        git_source = GitSource(key_path="/path/to/key with spaces")
        env = git_source._build_git_env()
        expected_key = shlex.quote("/path/to/key with spaces")
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn(expected_key, env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_with_ssh_env(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource(key_path="/path/to/key")
        result = git_source.clone_repo("git@github.com:user/repo.git", "/local/path", mirror=False)

        self.assertEqual(mock_repo, result)
        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@github.com:user/repo.git", call_args[0][0])
        self.assertEqual("/local/path", call_args[0][1])
        self.assertIn("env", call_args[1])
        self.assertIn("GIT_SSH_COMMAND", call_args[1]["env"])
        self.assertNotIn("mirror", call_args[1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_mirror_flag(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource()
        result = git_source.clone_repo("git@github.com:user/repo.git", "/local/mirror.git", mirror=True)

        self.assertEqual(mock_repo, result)
        call_args = mock_repo_class.clone_from.call_args
        self.assertTrue(call_args[1]["mirror"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_command_error(self, mock_repo_class):
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", "error message")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@github.com:user/repo.git", "/local/path", mirror=False)

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@github.com:user/repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_for_valid_path(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.open_repo("/valid/repo/path")

        self.assertEqual(mock_repo, result)
        mock_repo_class.assert_called_once_with("/valid/repo/path")

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_error_on_invalid_git_repository(self, mock_repo_class):
        mock_repo_class.side_effect = InvalidGitRepositoryError("/invalid/path")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/invalid/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/invalid/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_error_on_no_such_path(self, mock_repo_class):
        mock_repo_class.side_effect = NoSuchPathError("/missing/path")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/missing/path")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_remote_update_prune(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.git.remote.return_value = None
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.update_mirror("/mirror/path")

        self.assertEqual(mock_repo, result)
        mock_repo.git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_error_on_git_command_error(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", "update failed")
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/mirror/path")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/mirror/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.fetch_working_copy("/working/path")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_error_on_git_command_error(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "fetch failed")
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/working/path")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/working/path", str(context.exception))

    def test_checkout_branch_existing_local_branch(self):
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev", "feature"]

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "dev")

        mock_repo.git.checkout.assert_called_once_with("dev")

    def test_checkout_branch_creates_new_tracking_branch(self):
        mock_repo = Mock()
        mock_repo.heads = ["main"]

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "remote-branch")

        mock_repo.git.checkout.assert_called_once_with("-B", "remote-branch", "origin/remote-branch")

    def test_checkout_branch_raises_error_on_git_command_error(self):
        mock_repo = Mock()
        mock_repo.heads = ["main"]
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", "checkout failed")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "missing-branch")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("missing-branch", str(context.exception))

    def test_checkout_branch_handles_branch_name_with_special_characters(self):
        mock_repo = Mock()
        mock_repo.heads = []

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "feature/JIRA-123")

        mock_repo.git.checkout.assert_called_once_with("-B", "feature/JIRA-123", "origin/feature/JIRA-123")


if __name__ == "__main__":
    unittest.main()