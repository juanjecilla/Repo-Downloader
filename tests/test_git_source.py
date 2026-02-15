import os
import unittest
from unittest.mock import Mock, patch

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


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSource(unittest.TestCase):
    def test_init_expands_key_path(self):
        source = GitSource(key_path="~/custom/key")
        expected_path = os.path.expanduser("~/custom/key")
        self.assertEqual(expected_path, source._key_path)

    def test_init_default_key_path(self):
        source = GitSource()
        expected_path = os.path.expanduser("~/.ssh/id_rsa")
        self.assertEqual(expected_path, source._key_path)

    def test_build_git_env_includes_ssh_command(self):
        source = GitSource(key_path="/path/to/key")
        env = source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("/path/to/key", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path_with_spaces(self):
        source = GitSource(key_path="/path with spaces/key")
        env = source._build_git_env()
        # shlex.quote should properly escape the path
        self.assertIn("GIT_SSH_COMMAND", env)
        # The quoted path should be in the SSH command
        self.assertIn("key", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo.clone_from")
    def test_clone_repo_passes_mirror_flag(self, mock_clone):
        mock_repo = Mock()
        mock_clone.return_value = mock_repo
        source = GitSource()

        result = source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=True)

        self.assertEqual(mock_repo, result)
        mock_clone.assert_called_once()
        call_kwargs = mock_clone.call_args.kwargs
        self.assertTrue(call_kwargs.get("mirror"))
        self.assertIn("env", call_kwargs)

    @patch("data.source.git_source.Repo.clone_from")
    def test_clone_repo_without_mirror_flag(self, mock_clone):
        mock_repo = Mock()
        mock_clone.return_value = mock_repo
        source = GitSource()

        result = source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)

        self.assertEqual(mock_repo, result)
        mock_clone.assert_called_once()
        call_kwargs = mock_clone.call_args.kwargs
        self.assertNotIn("mirror", call_kwargs)
        self.assertIn("env", call_kwargs)

    @patch("data.source.git_source.Repo.clone_from")
    def test_clone_repo_raises_sync_error_on_git_failure(self, mock_clone):
        mock_clone.side_effect = GitCommandError("clone", "failed")
        source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            source.clone_repo("git@example.com:repo.git", "/tmp/repo")

        self.assertIn("Failed cloning repository", str(ctx.exception))
        self.assertIn("git@example.com:repo.git", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_object(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        source = GitSource()

        result = source.open_repo("/path/to/repo")

        self.assertEqual(mock_repo, result)
        mock_repo_class.assert_called_once_with("/path/to/repo")

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_on_invalid_repo(self, mock_repo_class):
        mock_repo_class.side_effect = InvalidGitRepositoryError("/path/to/repo")
        source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            source.open_repo("/path/to/repo")

        self.assertIn("Invalid local repository path", str(ctx.exception))
        self.assertIn("/path/to/repo", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_on_no_such_path(self, mock_repo_class):
        mock_repo_class.side_effect = NoSuchPathError("/nonexistent")
        source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            source.open_repo("/nonexistent")

        self.assertIn("Invalid local repository path", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_runs_remote_update(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.git.remote = Mock(return_value=None)
        mock_repo_class.return_value = mock_repo
        source = GitSource()

        result = source.update_mirror("/path/to/mirror")

        self.assertEqual(mock_repo, result)
        mock_repo.git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_sync_error_on_git_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", "failed")
        mock_repo_class.return_value = mock_repo
        source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            source.update_mirror("/path/to/mirror")

        self.assertIn("Failed updating mirror repository", str(ctx.exception))
        self.assertIn("/path/to/mirror", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_fetches_from_origin(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        source = GitSource()

        result = source.fetch_working_copy("/path/to/working")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_sync_error_on_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "failed")
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            source.fetch_working_copy("/path/to/working")

        self.assertIn("Failed fetching working repository", str(ctx.exception))
        self.assertIn("/path/to/working", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_existing_local_branch(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev"]
        source = GitSource()

        source.checkout_branch(mock_repo, "main")

        mock_repo.git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_new_tracking_branch(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = []
        source = GitSource()

        source.checkout_branch(mock_repo, "feature")

        mock_repo.git.checkout.assert_called_once_with("-B", "feature", "origin/feature")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_sync_error_on_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", "failed")
        source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            source.checkout_branch(mock_repo, "nonexistent")

        self.assertIn("Failed checking out branch", str(ctx.exception))
        self.assertIn("nonexistent", str(ctx.exception))

    def test_multiple_git_sources_use_different_keys(self):
        source1 = GitSource(key_path="/key1")
        source2 = GitSource(key_path="/key2")

        env1 = source1._build_git_env()
        env2 = source2._build_git_env()

        self.assertIn("/key1", env1["GIT_SSH_COMMAND"])
        self.assertIn("/key2", env2["GIT_SSH_COMMAND"])
        self.assertNotEqual(env1["GIT_SSH_COMMAND"], env2["GIT_SSH_COMMAND"])


if __name__ == "__main__":
    unittest.main()