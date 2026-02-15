import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from utils.errors import RepositorySyncError

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


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceInit(unittest.TestCase):
    def test_git_source_initializes_with_default_key_path(self):
        git_source = GitSource()
        self.assertIsNotNone(git_source._key_path)
        self.assertIn(".ssh/id_rsa", git_source._key_path)

    def test_git_source_initializes_with_custom_key_path(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        self.assertIn("custom_key", git_source._key_path)

    def test_git_source_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/.ssh/id_rsa")
        self.assertNotIn("~", git_source._key_path)


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceBuildEnv(unittest.TestCase):
    def test_build_git_env_includes_git_ssh_command(self):
        git_source = GitSource(key_path="/home/user/.ssh/id_rsa")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)

    def test_build_git_env_includes_key_path_in_command(self):
        git_source = GitSource(key_path="/home/user/.ssh/custom_key")
        env = git_source._build_git_env()
        self.assertIn("custom_key", env["GIT_SSH_COMMAND"])

    def test_build_git_env_includes_strict_host_key_checking(self):
        git_source = GitSource()
        env = git_source._build_git_env()
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path with spaces/id_rsa")
        env = git_source._build_git_env()
        command = env["GIT_SSH_COMMAND"]
        self.assertIn("ssh -i", command)


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceCloneRepo(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_repo_clone_from(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource()
        result = git_source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        mock_repo_class.clone_from.assert_called_once()
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_passes_mirror_flag(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource()
        git_source.clone_repo("git@example.com:repo.git", "/local/path", mirror=True)

        call_kwargs = mock_repo_class.clone_from.call_args.kwargs
        self.assertTrue(call_kwargs.get("mirror"))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_includes_env_in_clone_call(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource()
        git_source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        call_kwargs = mock_repo_class.clone_from.call_args.kwargs
        self.assertIn("env", call_kwargs)
        self.assertIn("GIT_SSH_COMMAND", call_kwargs["env"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_command_error(self, mock_repo_class):
        mock_repo_class.clone_from.side_effect = GitCommandError(
            "clone", 128, stderr="fatal: repository not found"
        )

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceOpenRepo(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_open_repo_calls_repo_constructor(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.open_repo("/local/path")

        mock_repo_class.assert_called_once_with("/local/path")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_invalid_git_repository(
        self, mock_repo_class
    ):
        mock_repo_class.side_effect = InvalidGitRepositoryError("Not a git repository")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/invalid/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/invalid/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_no_such_path(self, mock_repo_class):
        mock_repo_class.side_effect = NoSuchPathError("Path does not exist")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/nonexistent/path")

        self.assertIn("Invalid local repository path", str(context.exception))


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceUpdateMirror(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_remote_update_with_prune(self, mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.update_mirror("/local/mirror.git")

        mock_git.remote.assert_called_once_with("update", "--prune")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_repository_sync_error_on_git_command_error(
        self, mock_repo_class
    ):
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("remote", 1, stderr="fetch failed")
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/local/mirror.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/local/mirror.git", str(context.exception))


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceFetchWorkingCopy(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch_with_prune_and_tags(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.fetch_working_copy("/local/working")

        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_repository_sync_error_on_git_command_error(
        self, mock_repo_class
    ):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", 1, stderr="connection refused")
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/local/working")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/local/working", str(context.exception))


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceCheckoutBranch(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_checkout_branch_checks_out_existing_local_branch(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev"]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_tracking_branch_for_remote_only(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main"]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "dev")

        mock_git.checkout.assert_called_once_with("-B", "dev", "origin/dev")

    def test_checkout_branch_raises_repository_sync_error_on_git_command_error(self):
        mock_repo = Mock()
        mock_repo.heads = []
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError(
            "checkout", 1, stderr="pathspec 'dev' did not match"
        )
        mock_repo.git = mock_git

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "dev")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("'dev'", str(context.exception))


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceEdgeCases(unittest.TestCase):
    def test_git_source_handles_key_path_with_spaces(self):
        git_source = GitSource(key_path="/path with spaces/id_rsa")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_preserves_original_exception_context(self, mock_repo_class):
        original_error = GitCommandError("clone", 128, stderr="original error message")
        mock_repo_class.clone_from.side_effect = original_error

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:repo.git", "/local/path")

        self.assertIsNotNone(context.exception.__cause__)
        self.assertIsInstance(context.exception.__cause__, GitCommandError)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_preserves_original_exception_context(self, mock_repo_class):
        mock_repo = Mock()
        original_error = GitCommandError("remote", 1, stderr="fetch failed")
        mock_repo.git.remote.side_effect = original_error
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/local/mirror.git")

        self.assertIsNotNone(context.exception.__cause__)

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_preserves_original_exception_context(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = []
        original_error = GitCommandError("checkout", 1, stderr="branch not found")
        mock_repo.git.checkout.side_effect = original_error

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "nonexistent")

        self.assertIsNotNone(context.exception.__cause__)


if __name__ == "__main__":
    unittest.main()