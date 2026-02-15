import os
import shlex
import unittest
from unittest.mock import MagicMock, Mock, patch

from utils.errors import RepositorySyncError

try:
    from git import Repo
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
    from data.source.git_source import GitSource
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    Repo = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    GitSource = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git_source tests")
class TestGitSource(unittest.TestCase):
    def test_init_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        self.assertTrue(git_source._key_path.startswith(os.path.expanduser("~")))
        self.assertNotIn("~", git_source._key_path)

    def test_init_uses_default_key_path(self):
        git_source = GitSource()
        self.assertTrue(git_source._key_path.endswith(".ssh/id_rsa"))

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path/with spaces/id_rsa")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        quoted_path = shlex.quote("/path/with spaces/id_rsa")
        self.assertIn(quoted_path, env["GIT_SSH_COMMAND"])

    def test_build_git_env_includes_strict_host_key_checking(self):
        git_source = GitSource()
        env = git_source._build_git_env()
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_with_env(self, mock_repo_cls):
        mock_repo = Mock()
        mock_repo_cls.clone_from.return_value = mock_repo

        git_source = GitSource(key_path="/test/key")
        result = git_source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)

        self.assertEqual(mock_repo, result)
        mock_repo_cls.clone_from.assert_called_once()
        call_args = mock_repo_cls.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/tmp/repo", call_args[0][1])
        self.assertIn("env", call_args[1])
        self.assertIn("GIT_SSH_COMMAND", call_args[1]["env"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_mirror_passes_mirror_flag(self, mock_repo_cls):
        mock_repo = Mock()
        mock_repo_cls.clone_from.return_value = mock_repo

        git_source = GitSource()
        git_source.clone_repo("git@example.com:repo.git", "/tmp/repo.git", mirror=True)

        call_args = mock_repo_cls.clone_from.call_args
        self.assertTrue(call_args[1].get("mirror"))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_failure(self, mock_repo_cls):
        mock_repo_cls.clone_from.side_effect = GitCommandError("clone", 128)

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)

        self.assertIn("Failed cloning repository", str(ctx.exception))
        self.assertIn("git@example.com:repo.git", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_instance(self, mock_repo_cls):
        mock_repo = Mock()
        mock_repo_cls.return_value = mock_repo

        git_source = GitSource()
        result = git_source.open_repo("/path/to/repo")

        self.assertEqual(mock_repo, result)
        mock_repo_cls.assert_called_once_with("/path/to/repo")

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_on_invalid_git_repository(self, mock_repo_cls):
        mock_repo_cls.side_effect = InvalidGitRepositoryError("/bad/path")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.open_repo("/bad/path")

        self.assertIn("Invalid local repository path", str(ctx.exception))
        self.assertIn("/bad/path", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_on_no_such_path(self, mock_repo_cls):
        mock_repo_cls.side_effect = NoSuchPathError("/missing/path")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.open_repo("/missing/path")

        self.assertIn("Invalid local repository path", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_remote_update_with_prune(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        git_source = GitSource()
        result = git_source.update_mirror("/path/to/mirror.git")

        self.assertEqual(mock_repo, result)
        mock_repo.git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_on_git_command_error(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", 128)
        mock_repo_cls.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.update_mirror("/path/to/mirror.git")

        self.assertIn("Failed updating mirror repository", str(ctx.exception))
        self.assertIn("/path/to/mirror.git", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch_with_prune_and_tags(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_origin = MagicMock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_cls.return_value = mock_repo

        git_source = GitSource()
        result = git_source.fetch_working_copy("/path/to/working")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_on_git_command_error(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_origin = MagicMock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", 128)
        mock_repo.remotes.origin = mock_origin
        mock_repo_cls.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.fetch_working_copy("/path/to/working")

        self.assertIn("Failed fetching working repository", str(ctx.exception))
        self.assertIn("/path/to/working", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_when_branch_exists_locally(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.heads = ["main", "dev"]

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "main")

        mock_repo.git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_tracking_branch_if_not_local(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.heads = ["main"]

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "feature")

        mock_repo.git.checkout.assert_called_once_with("-B", "feature", "origin/feature")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_on_git_command_error(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", 128)

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.checkout_branch(mock_repo, "missing-branch")

        self.assertIn("Failed checking out branch", str(ctx.exception))
        self.assertIn("missing-branch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()