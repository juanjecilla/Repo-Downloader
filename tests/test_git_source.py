import importlib.util
import os
import unittest
from unittest.mock import Mock, patch, MagicMock

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
    def test_init_with_default_key_path(self):
        git_source = GitSource()
        # Key path should be expanded
        self.assertTrue(git_source._key_path.startswith(os.path.expanduser("~")))

    def test_init_with_custom_key_path(self):
        custom_path = "~/.ssh/custom_key"
        git_source = GitSource(key_path=custom_path)
        expected_path = os.path.expanduser(custom_path)
        self.assertEqual(expected_path, git_source._key_path)

    def test_build_git_env_creates_ssh_command(self):
        git_source = GitSource(key_path="/path/to/key")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])
        self.assertIn("/path/to/key", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path with spaces/key")
        env = git_source._build_git_env()
        # Should be safely quoted
        self.assertIn("GIT_SSH_COMMAND", env)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_success_without_mirror(self, mock_repo):
        mock_repo_instance = Mock()
        mock_repo.clone_from.return_value = mock_repo_instance

        git_source = GitSource()
        result = git_source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)

        self.assertEqual(mock_repo_instance, result)
        mock_repo.clone_from.assert_called_once()
        call_args = mock_repo.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/tmp/repo", call_args[0][1])
        self.assertIn("env", call_args[1])
        self.assertNotIn("mirror", call_args[1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_success_with_mirror(self, mock_repo):
        mock_repo_instance = Mock()
        mock_repo.clone_from.return_value = mock_repo_instance

        git_source = GitSource()
        result = git_source.clone_repo("git@example.com:repo.git", "/tmp/repo.git", mirror=True)

        self.assertEqual(mock_repo_instance, result)
        call_args = mock_repo.clone_from.call_args
        self.assertIn("mirror", call_args[1])
        self.assertTrue(call_args[1]["mirror"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_failure(self, mock_repo):
        mock_repo.clone_from.side_effect = GitCommandError("clone", "Clone failed")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo")

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_success(self, mock_repo_class):
        mock_repo_instance = Mock()
        mock_repo_class.return_value = mock_repo_instance

        git_source = GitSource()
        result = git_source.open_repo("/path/to/repo")

        self.assertEqual(mock_repo_instance, result)
        mock_repo_class.assert_called_once_with("/path/to/repo")

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_error_for_invalid_repository(self, mock_repo_class):
        mock_repo_class.side_effect = InvalidGitRepositoryError()

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/invalid/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/invalid/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_error_for_missing_path(self, mock_repo_class):
        mock_repo_class.side_effect = NoSuchPathError()

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/nonexistent/path")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_success(self, mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.update_mirror("/path/to/mirror.git")

        self.assertEqual(mock_repo, result)
        mock_git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_error_on_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("remote", "Update failed")
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/path/to/mirror.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/path/to/mirror.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_success(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.fetch_working_copy("/path/to/working")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_error_on_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "Fetch failed")
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/path/to/working")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/path/to/working", str(context.exception))

    def test_checkout_branch_existing_local_branch(self):
        mock_repo = Mock()
        mock_head = Mock()
        mock_head.name = "main"
        mock_repo.heads = [mock_head]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    def test_checkout_branch_new_from_remote(self):
        mock_repo = Mock()
        mock_head = Mock()
        mock_head.name = "main"
        mock_repo.heads = [mock_head]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "feature")

        mock_git.checkout.assert_called_once_with("-B", "feature", "origin/feature")

    def test_checkout_branch_raises_error_on_failure(self):
        mock_repo = Mock()
        mock_repo.heads = []
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError("checkout", "Checkout failed")
        mock_repo.git = mock_git

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "nonexistent")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("nonexistent", str(context.exception))

    def test_checkout_branch_checks_heads_list(self):
        """Test that checkout_branch properly checks if branch exists in heads."""
        mock_repo = Mock()
        mock_head1 = Mock()
        mock_head1.name = "main"
        mock_head2 = Mock()
        mock_head2.name = "develop"
        mock_repo.heads = [mock_head1, mock_head2]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()

        # Should find 'main' in heads
        git_source.checkout_branch(mock_repo, "main")
        mock_git.checkout.assert_called_with("main")

        # Should not find 'feature' in heads
        mock_git.reset_mock()
        git_source.checkout_branch(mock_repo, "feature")
        mock_git.checkout.assert_called_with("-B", "feature", "origin/feature")


if __name__ == "__main__":
    unittest.main()