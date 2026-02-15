import os
import tempfile
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
    GitSource = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_init_expands_tilde_in_key_path(self):
        source = GitSource(key_path="~/.ssh/custom_key")
        self.assertNotIn("~", source._key_path)
        self.assertTrue(source._key_path.endswith(".ssh/custom_key"))

    def test_build_git_env_quotes_key_path_with_spaces(self):
        source = GitSource(key_path="/path/with spaces/key")
        env = source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        # shlex.quote should handle the spaces
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])

    def test_build_git_env_includes_strict_host_key_checking(self):
        source = GitSource(key_path="/path/to/key")
        env = source._build_git_env()
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_clone_repo_raises_repository_sync_error_on_git_failure(self):
        source = GitSource()
        with patch.object(Repo, "clone_from") as mock_clone:
            mock_clone.side_effect = GitCommandError("clone", "failed")
            with self.assertRaises(RepositorySyncError) as ctx:
                source.clone_repo("git@example.com:repo.git", "/tmp/repo")
            self.assertIn("Failed cloning repository", str(ctx.exception))
            self.assertIn("git@example.com:repo.git", str(ctx.exception))

    def test_clone_repo_passes_mirror_flag(self):
        source = GitSource()
        with patch.object(Repo, "clone_from") as mock_clone:
            mock_clone.return_value = Mock()
            source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=True)
            mock_clone.assert_called_once()
            call_kwargs = mock_clone.call_args[1]
            self.assertTrue(call_kwargs.get("mirror"))

    def test_clone_repo_does_not_pass_mirror_flag_when_false(self):
        source = GitSource()
        with patch.object(Repo, "clone_from") as mock_clone:
            mock_clone.return_value = Mock()
            source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)
            mock_clone.assert_called_once()
            call_kwargs = mock_clone.call_args[1]
            self.assertNotIn("mirror", call_kwargs)

    def test_open_repo_raises_repository_sync_error_on_invalid_path(self):
        source = GitSource()
        with patch.object(Repo, "__init__") as mock_init:
            mock_init.side_effect = NoSuchPathError("/nonexistent")
            with self.assertRaises(RepositorySyncError) as ctx:
                source.open_repo("/nonexistent")
            self.assertIn("Invalid local repository path", str(ctx.exception))

    def test_open_repo_raises_repository_sync_error_on_invalid_git_repo(self):
        source = GitSource()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(RepositorySyncError) as ctx:
                source.open_repo(tmp_dir)
            self.assertIn("Invalid local repository path", str(ctx.exception))

    def test_update_mirror_raises_repository_sync_error_on_git_failure(self):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", "failed")

        with patch.object(source, "open_repo", return_value=mock_repo):
            with self.assertRaises(RepositorySyncError) as ctx:
                source.update_mirror("/tmp/repo")
            self.assertIn("Failed updating mirror repository", str(ctx.exception))

    def test_update_mirror_calls_git_remote_update_with_prune(self):
        source = GitSource()
        mock_repo = MagicMock()

        with patch.object(source, "open_repo", return_value=mock_repo):
            result = source.update_mirror("/tmp/repo")
            mock_repo.git.remote.assert_called_once_with("update", "--prune")
            self.assertEqual(mock_repo, result)

    def test_fetch_working_copy_raises_repository_sync_error_on_git_failure(self):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo.remotes.origin.fetch.side_effect = GitCommandError("fetch", "failed")

        with patch.object(source, "open_repo", return_value=mock_repo):
            with self.assertRaises(RepositorySyncError) as ctx:
                source.fetch_working_copy("/tmp/repo")
            self.assertIn("Failed fetching working repository", str(ctx.exception))

    def test_fetch_working_copy_calls_origin_fetch_with_prune_and_tags(self):
        source = GitSource()
        mock_repo = MagicMock()

        with patch.object(source, "open_repo", return_value=mock_repo):
            result = source.fetch_working_copy("/tmp/repo")
            mock_repo.remotes.origin.fetch.assert_called_once_with(prune=True, tags=True)
            self.assertEqual(mock_repo, result)

    def test_checkout_branch_creates_tracking_branch_when_not_exists_locally(self):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo.heads = []

        source.checkout_branch(mock_repo, "feature-branch")
        mock_repo.git.checkout.assert_called_once_with(
            "-B", "feature-branch", "origin/feature-branch"
        )

    def test_checkout_branch_checks_out_existing_local_branch(self):
        source = GitSource()
        mock_repo = MagicMock()
        mock_head = MagicMock()
        mock_head.name = "main"
        mock_repo.heads = ["main"]
        mock_repo.heads.__contains__ = lambda self, item: item == "main"

        source.checkout_branch(mock_repo, "main")
        mock_repo.git.checkout.assert_called_once_with("main")

    def test_checkout_branch_raises_repository_sync_error_on_git_failure(self):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", "failed")

        with self.assertRaises(RepositorySyncError) as ctx:
            source.checkout_branch(mock_repo, "feature-branch")
        self.assertIn("Failed checking out branch", str(ctx.exception))
        self.assertIn("feature-branch", str(ctx.exception))

    def test_clone_repo_passes_git_env_to_clone_from(self):
        source = GitSource(key_path="/custom/key")
        with patch.object(Repo, "clone_from") as mock_clone:
            mock_clone.return_value = Mock()
            source.clone_repo("git@example.com:repo.git", "/tmp/repo")
            call_kwargs = mock_clone.call_args[1]
            self.assertIn("env", call_kwargs)
            self.assertIn("GIT_SSH_COMMAND", call_kwargs["env"])

    def test_default_key_path_is_home_ssh_id_rsa(self):
        source = GitSource()
        self.assertTrue(source._key_path.endswith(".ssh/id_rsa"))


if __name__ == "__main__":
    unittest.main()