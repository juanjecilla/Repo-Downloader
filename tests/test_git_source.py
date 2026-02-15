import os
import unittest
from unittest.mock import MagicMock, Mock, patch

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


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSource(unittest.TestCase):
    def test_build_git_env_with_default_key_path(self):
        git_source = GitSource()
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])
        self.assertIn("-o StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_with_custom_key_path(self):
        git_source = GitSource(key_path="/custom/path/key")
        env = git_source._build_git_env()
        self.assertIn("/custom/path/key", env["GIT_SSH_COMMAND"])

    def test_build_git_env_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        expanded_path = os.path.expanduser("~/.ssh/custom_key")
        self.assertEqual(expanded_path, git_source._key_path)

    def test_build_git_env_escapes_special_characters_in_key_path(self):
        git_source = GitSource(key_path="/path with spaces/key")
        env = git_source._build_git_env()
        # Should use shlex.quote to properly escape the path
        self.assertIn("GIT_SSH_COMMAND", env)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_mirror_mode(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_cls.clone_from.return_value = mock_repo

        result = git_source.clone_repo("git@example.com:repo.git", "/tmp/repo.git", mirror=True)

        mock_repo_cls.clone_from.assert_called_once()
        call_kwargs = mock_repo_cls.clone_from.call_args[1]
        self.assertTrue(call_kwargs["mirror"])
        self.assertIn("env", call_kwargs)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_working_mode(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_cls.clone_from.return_value = mock_repo

        result = git_source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)

        mock_repo_cls.clone_from.assert_called_once()
        call_kwargs = mock_repo_cls.clone_from.call_args[1]
        self.assertNotIn("mirror", call_kwargs)
        self.assertIn("env", call_kwargs)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_command_error(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo_cls.clone_from.side_effect = GitCommandError("clone", 128)

        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_success(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_cls.return_value = mock_repo

        result = git_source.open_repo("/tmp/repo")

        mock_repo_cls.assert_called_once_with("/tmp/repo")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_error_on_invalid_repository(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo_cls.side_effect = InvalidGitRepositoryError("/tmp/invalid")

        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/tmp/invalid")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/tmp/invalid", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_error_on_no_such_path(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo_cls.side_effect = NoSuchPathError("/tmp/nonexistent")

        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/tmp/nonexistent")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/tmp/nonexistent", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_success(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_cls.return_value = mock_repo

        result = git_source.update_mirror("/tmp/repo.git")

        mock_repo.git.remote.assert_called_once_with("update", "--prune")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_error_on_git_command_error(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", 128)
        mock_repo_cls.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/tmp/repo.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/tmp/repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_success(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_cls.return_value = mock_repo

        result = git_source.fetch_working_copy("/tmp/repo")

        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_error_on_git_command_error(self, mock_repo_cls):
        git_source = GitSource()
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", 128)
        mock_repo.remotes.origin = mock_origin
        mock_repo_cls.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/tmp/repo")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/tmp/repo", str(context.exception))

    def test_checkout_branch_existing_local_branch(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev"]

        git_source.checkout_branch(mock_repo, "main")

        mock_repo.git.checkout.assert_called_once_with("main")

    def test_checkout_branch_remote_only_branch(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = []

        git_source.checkout_branch(mock_repo, "feature")

        mock_repo.git.checkout.assert_called_once_with("-B", "feature", "origin/feature")

    def test_checkout_branch_raises_error_on_git_command_error(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", 128)

        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "nonexistent")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("nonexistent", str(context.exception))

    def test_checkout_branch_uses_correct_branch_for_local_vs_remote(self):
        git_source = GitSource()

        # Test local branch exists
        mock_repo_local = Mock()
        mock_repo_local.heads = ["existing-branch"]
        git_source.checkout_branch(mock_repo_local, "existing-branch")
        mock_repo_local.git.checkout.assert_called_with("existing-branch")

        # Test remote-only branch
        mock_repo_remote = Mock()
        mock_repo_remote.heads = []
        git_source.checkout_branch(mock_repo_remote, "remote-branch")
        mock_repo_remote.git.checkout.assert_called_with("-B", "remote-branch", "origin/remote-branch")


if __name__ == "__main__":
    unittest.main()