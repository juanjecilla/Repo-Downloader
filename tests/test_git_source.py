import importlib.util
import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from utils.errors import RepositorySyncError


GITPYTHON_AVAILABLE = importlib.util.find_spec("git") is not None
if GITPYTHON_AVAILABLE:
    from data.source.git_source import GitSource
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
else:
    GitSource = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_init_expands_tilde_in_key_path(self):
        with patch.dict("os.environ", {"HOME": "/home/testuser"}, clear=False):
            git_source = GitSource(key_path="~/.ssh/id_rsa")
            self.assertEqual("/home/testuser/.ssh/id_rsa", git_source._key_path)

    def test_init_uses_default_key_path(self):
        git_source = GitSource()
        self.assertTrue(git_source._key_path.endswith("/.ssh/id_rsa"))

    def test_build_git_env_includes_ssh_command_with_key_path(self):
        git_source = GitSource(key_path="/custom/path/id_rsa")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("/custom/path/id_rsa", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path with spaces/id_rsa")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("'/path with spaces/id_rsa'", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_with_mirror_true(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo
        git_source = GitSource()

        result = git_source.clone_repo(
            "git@example.com:acme/repo.git",
            "/tmp/repo.git",
            mirror=True,
        )

        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:acme/repo.git", call_args[0][0])
        self.assertEqual("/tmp/repo.git", call_args[0][1])
        self.assertTrue(call_args[1]["mirror"])
        self.assertIn("env", call_args[1])
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_with_mirror_false(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo
        git_source = GitSource()

        result = git_source.clone_repo(
            "git@example.com:acme/repo.git",
            "/tmp/repo",
            mirror=False,
        )

        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:acme/repo.git", call_args[0][0])
        self.assertEqual("/tmp/repo", call_args[0][1])
        self.assertNotIn("mirror", call_args[1])
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_command_error(self, mock_repo_class):
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", "Failed")
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:acme/repo.git", "/tmp/repo.git", mirror=True)

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:acme/repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_for_valid_path(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        result = git_source.open_repo("/valid/repo/path")

        mock_repo_class.assert_called_once_with("/valid/repo/path")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_invalid_git_repository(
        self, mock_repo_class
    ):
        mock_repo_class.side_effect = InvalidGitRepositoryError()
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/invalid/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/invalid/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_no_such_path(self, mock_repo_class):
        mock_repo_class.side_effect = NoSuchPathError()
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/nonexistent/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/nonexistent/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_git_remote_update_with_prune(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        result = git_source.update_mirror("/tmp/repo.git")

        mock_repo.git.remote.assert_called_once_with("update", "--prune")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_repository_sync_error_on_git_command_error(
        self, mock_repo_class
    ):
        mock_repo = Mock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", "Failed")
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/tmp/repo.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/tmp/repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch_with_prune_and_tags(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        result = git_source.fetch_working_copy("/tmp/repo")

        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_repository_sync_error_on_git_command_error(
        self, mock_repo_class
    ):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "Network error")
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/tmp/repo")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/tmp/repo", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_checks_out_existing_local_branch(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev"]
        git_source = GitSource()

        git_source.checkout_branch(mock_repo, "dev")

        mock_repo.git.checkout.assert_called_once_with("dev")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_and_checks_out_remote_tracking_branch(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main"]
        git_source = GitSource()

        git_source.checkout_branch(mock_repo, "dev")

        mock_repo.git.checkout.assert_called_once_with("-B", "dev", "origin/dev")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_repository_sync_error_on_git_command_error(
        self, mock_repo_class
    ):
        mock_repo = Mock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", "Branch not found")
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "missing-branch")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("missing-branch", str(context.exception))

    def test_clone_repo_with_invalid_url_raises_repository_sync_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            git_source = GitSource()
            target_path = os.path.join(tmp_dir, "test-repo.git")

            with self.assertRaises(RepositorySyncError) as context:
                git_source.clone_repo("invalid-git-url", target_path, mirror=True)

            self.assertIn("Failed cloning repository", str(context.exception))

    def test_open_repo_with_file_path_raises_repository_sync_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "not-a-repo.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("test")

            git_source = GitSource()
            with self.assertRaises(RepositorySyncError) as context:
                git_source.open_repo(file_path)

            self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_passes_custom_env_to_git(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo
        git_source = GitSource(key_path="/custom/key")

        git_source.clone_repo("git@example.com:acme/repo.git", "/tmp/repo", mirror=False)

        call_kwargs = mock_repo_class.clone_from.call_args[1]
        self.assertIn("env", call_kwargs)
        self.assertIn("GIT_SSH_COMMAND", call_kwargs["env"])
        self.assertIn("/custom/key", call_kwargs["env"]["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_update_mirror_opens_repo_before_update(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        git_source.update_mirror("/tmp/mirror.git")

        mock_repo_class.assert_called_once_with("/tmp/mirror.git")
        mock_repo.git.remote.assert_called_once()

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_opens_repo_before_fetch(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        git_source.fetch_working_copy("/tmp/working")

        mock_repo_class.assert_called_once_with("/tmp/working")
        mock_origin.fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()