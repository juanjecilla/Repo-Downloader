import os
import shlex
import unittest
from unittest.mock import Mock, patch, MagicMock

try:
    from git import Repo
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
    from data.source.git_source import GitSource
    from utils.errors import RepositorySyncError
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    Repo = None
    GitSource = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    RepositorySyncError = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_init_stores_key_path(self):
        git_source = GitSource(key_path="/custom/key")
        self.assertEqual("/custom/key", git_source._key_path)

    def test_init_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/.ssh/id_rsa")
        self.assertNotIn("~", git_source._key_path)
        self.assertTrue(git_source._key_path.endswith(".ssh/id_rsa"))

    def test_build_git_env_includes_ssh_command_with_key(self):
        git_source = GitSource(key_path="/tmp/test_key")
        env = git_source._build_git_env()

        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("/tmp/test_key", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path with spaces/key")
        env = git_source._build_git_env()

        expected_quoted = shlex.quote("/path with spaces/key")
        self.assertIn(expected_quoted, env["GIT_SSH_COMMAND"])

    @patch('data.source.git_source.Repo')
    def test_clone_repo_calls_clone_from_with_env(self, mock_repo_class):
        git_source = GitSource(key_path="/tmp/key")
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        result = git_source.clone_repo("git@example.com:test.git", "/tmp/local", mirror=False)

        self.assertEqual(mock_repo, result)
        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:test.git", call_args[0][0])
        self.assertEqual("/tmp/local", call_args[0][1])
        self.assertIn("env", call_args[1])
        self.assertIn("GIT_SSH_COMMAND", call_args[1]["env"])

    @patch('data.source.git_source.Repo')
    def test_clone_repo_mirror_passes_mirror_flag(self, mock_repo_class):
        git_source = GitSource(key_path="/tmp/key")
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        result = git_source.clone_repo("git@example.com:test.git", "/tmp/local", mirror=True)

        self.assertEqual(mock_repo, result)
        call_args = mock_repo_class.clone_from.call_args
        self.assertTrue(call_args[1].get("mirror"))

    @patch('data.source.git_source.Repo')
    def test_clone_repo_raises_sync_error_on_git_failure(self, mock_repo_class):
        git_source = GitSource(key_path="/tmp/key")
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", "failed")

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.clone_repo("git@example.com:test.git", "/tmp/local", mirror=False)

        self.assertIn("Failed cloning repository", str(ctx.exception))
        self.assertIn("git@example.com:test.git", str(ctx.exception))

    @patch('data.source.git_source.Repo')
    def test_open_repo_returns_repo_object(self, mock_repo_class):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        result = git_source.open_repo("/tmp/existing")

        self.assertEqual(mock_repo, result)
        mock_repo_class.assert_called_once_with("/tmp/existing")

    @patch('data.source.git_source.Repo')
    def test_open_repo_raises_sync_error_on_invalid_repo(self, mock_repo_class):
        git_source = GitSource()
        mock_repo_class.side_effect = InvalidGitRepositoryError("/bad/path")

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.open_repo("/bad/path")

        self.assertIn("Invalid local repository path", str(ctx.exception))
        self.assertIn("/bad/path", str(ctx.exception))

    @patch('data.source.git_source.Repo')
    def test_open_repo_raises_sync_error_on_no_such_path(self, mock_repo_class):
        git_source = GitSource()
        mock_repo_class.side_effect = NoSuchPathError

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.open_repo("/nonexistent")

        self.assertIn("Invalid local repository path", str(ctx.exception))

    @patch('data.source.git_source.Repo')
    def test_update_mirror_calls_remote_update(self, mock_repo_class):
        git_source = GitSource()
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        result = git_source.update_mirror("/tmp/mirror.git")

        self.assertEqual(mock_repo, result)
        mock_git.remote.assert_called_once_with("update", "--prune")

    @patch('data.source.git_source.Repo')
    def test_update_mirror_raises_sync_error_on_failure(self, mock_repo_class):
        git_source = GitSource()
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("remote", "failed")
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.update_mirror("/tmp/mirror.git")

        self.assertIn("Failed updating mirror repository", str(ctx.exception))
        self.assertIn("/tmp/mirror.git", str(ctx.exception))

    @patch('data.source.git_source.Repo')
    def test_fetch_working_copy_calls_origin_fetch(self, mock_repo_class):
        git_source = GitSource()
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        result = git_source.fetch_working_copy("/tmp/working")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch('data.source.git_source.Repo')
    def test_fetch_working_copy_raises_sync_error_on_failure(self, mock_repo_class):
        git_source = GitSource()
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "failed")
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.fetch_working_copy("/tmp/working")

        self.assertIn("Failed fetching working repository", str(ctx.exception))
        self.assertIn("/tmp/working", str(ctx.exception))

    def test_checkout_branch_checks_out_existing_branch(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo.heads = ["main", "dev"]

        git_source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    def test_checkout_branch_creates_new_branch_from_origin(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo.heads = ["main"]

        git_source.checkout_branch(mock_repo, "feature")

        mock_git.checkout.assert_called_once_with("-B", "feature", "origin/feature")

    def test_checkout_branch_raises_sync_error_on_failure(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError("checkout", "failed")
        mock_repo.git = mock_git
        mock_repo.heads = ["main"]

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.checkout_branch(mock_repo, "dev")

        self.assertIn("Failed checking out branch", str(ctx.exception))
        self.assertIn("dev", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()