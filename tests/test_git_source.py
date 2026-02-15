import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

try:
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
    from data.source.git_source import GitSource
    from utils.errors import RepositorySyncError
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    GitSource = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    RepositorySyncError = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_build_git_env_includes_ssh_key_path(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/.ssh/id_rsa")
        env = git_source._build_git_env()
        self.assertNotIn("~", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path/with spaces/key")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)

    def test_clone_repo_mirror_sets_mirror_flag(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo_class:
            mock_repo_class.clone_from.return_value = MagicMock()
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo.git", mirror=True)

            mock_repo_class.clone_from.assert_called_once()
            call_kwargs = mock_repo_class.clone_from.call_args[1]
            self.assertTrue(call_kwargs.get("mirror"))
            self.assertIn("env", call_kwargs)

    def test_clone_repo_working_omits_mirror_flag(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo_class:
            mock_repo_class.clone_from.return_value = MagicMock()
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)

            mock_repo_class.clone_from.assert_called_once()
            call_kwargs = mock_repo_class.clone_from.call_args[1]
            self.assertNotIn("mirror", call_kwargs)

    def test_clone_repo_raises_on_git_command_error(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo_class:
            mock_repo_class.clone_from.side_effect = GitCommandError("clone", "error")
            with self.assertRaises(RepositorySyncError) as context:
                git_source.clone_repo("git@example.com:repo.git", "/tmp/repo")

            self.assertIn("Failed cloning repository", str(context.exception))

    def test_open_repo_returns_repo_instance(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("data.source.git_source.Repo") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo_class.return_value = mock_repo
                git_source = GitSource()
                result = git_source.open_repo(tmp_dir)

                self.assertEqual(mock_repo, result)
                mock_repo_class.assert_called_once_with(tmp_dir)

    def test_open_repo_raises_on_invalid_git_repository_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("data.source.git_source.Repo") as mock_repo_class:
                mock_repo_class.side_effect = InvalidGitRepositoryError(tmp_dir)
                git_source = GitSource()
                with self.assertRaises(RepositorySyncError) as context:
                    git_source.open_repo(tmp_dir)

                self.assertIn("Invalid local repository path", str(context.exception))

    def test_open_repo_raises_on_no_such_path_error(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo_class:
            mock_repo_class.side_effect = NoSuchPathError("/nonexistent/path")
            with self.assertRaises(RepositorySyncError) as context:
                git_source.open_repo("/nonexistent/path")

            self.assertIn("Invalid local repository path", str(context.exception))

    def test_update_mirror_calls_remote_update_prune(self):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_git = MagicMock()
        mock_repo.git = mock_git

        with patch.object(git_source, "open_repo", return_value=mock_repo):
            result = git_source.update_mirror("/tmp/repo.git")

            mock_git.remote.assert_called_once_with("update", "--prune")
            self.assertEqual(mock_repo, result)

    def test_update_mirror_raises_on_git_command_error(self):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_repo.git.remote.side_effect = GitCommandError("remote update", "error")

        with patch.object(git_source, "open_repo", return_value=mock_repo):
            with self.assertRaises(RepositorySyncError) as context:
                git_source.update_mirror("/tmp/repo.git")

            self.assertIn("Failed updating mirror repository", str(context.exception))

    def test_fetch_working_copy_calls_origin_fetch(self):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_origin = MagicMock()
        mock_repo.remotes.origin = mock_origin

        with patch.object(git_source, "open_repo", return_value=mock_repo):
            result = git_source.fetch_working_copy("/tmp/repo")

            mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
            self.assertEqual(mock_repo, result)

    def test_fetch_working_copy_raises_on_git_command_error(self):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_origin = MagicMock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "error")
        mock_repo.remotes.origin = mock_origin

        with patch.object(git_source, "open_repo", return_value=mock_repo):
            with self.assertRaises(RepositorySyncError) as context:
                git_source.fetch_working_copy("/tmp/repo")

            self.assertIn("Failed fetching working repository", str(context.exception))

    def test_checkout_branch_existing_local_branch(self):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_heads = Mock()
        mock_heads.__contains__ = Mock(return_value=True)
        mock_repo.heads = mock_heads
        mock_git = MagicMock()
        mock_repo.git = mock_git

        git_source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    def test_checkout_branch_new_tracking_branch(self):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_heads = Mock()
        mock_heads.__contains__ = Mock(return_value=False)
        mock_repo.heads = mock_heads
        mock_git = MagicMock()
        mock_repo.git = mock_git

        git_source.checkout_branch(mock_repo, "feature-branch")

        mock_git.checkout.assert_called_once_with("-B", "feature-branch", "origin/feature-branch")

    def test_checkout_branch_raises_on_git_command_error(self):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_heads = Mock()
        mock_heads.__contains__ = Mock(return_value=True)
        mock_repo.heads = mock_heads
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", "error")

        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "main")

        self.assertIn("Failed checking out branch 'main'", str(context.exception))

    def test_checkout_branch_remote_branch_does_not_exist(self):
        git_source = GitSource()
        mock_repo = MagicMock()
        mock_heads = Mock()
        mock_heads.__contains__ = Mock(return_value=False)
        mock_repo.heads = mock_heads
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", "pathspec 'origin/nonexistent' did not match")

        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "nonexistent")

        self.assertIn("Failed checking out branch 'nonexistent'", str(context.exception))

    def test_git_source_default_key_path(self):
        git_source = GitSource()
        self.assertEqual(os.path.expanduser("~/.ssh/id_rsa"), git_source._key_path)

    def test_git_source_custom_key_path(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        self.assertEqual(os.path.expanduser("~/.ssh/custom_key"), git_source._key_path)


if __name__ == "__main__":
    unittest.main()