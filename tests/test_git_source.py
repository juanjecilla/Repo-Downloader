import os
import shlex
import unittest
from unittest.mock import Mock, patch, MagicMock

try:
    from data.source.git_source import GitSource
    from utils.errors import RepositorySyncError
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    GitSource = None
    RepositorySyncError = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source unit tests")
class TestGitSource(unittest.TestCase):
    def test_init_with_default_key_path(self):
        git_source = GitSource()
        expected_path = os.path.expanduser("~/.ssh/id_rsa")
        self.assertEqual(expected_path, git_source._key_path)

    def test_init_with_custom_key_path(self):
        custom_path = "/custom/path/to/key"
        git_source = GitSource(key_path=custom_path)
        self.assertEqual(custom_path, git_source._key_path)

    def test_init_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/custom/key")
        expected_path = os.path.expanduser("~/custom/key")
        self.assertEqual(expected_path, git_source._key_path)

    def test_build_git_env_returns_ssh_command_with_key(self):
        git_source = GitSource(key_path="/path/to/key")
        env = git_source._build_git_env()

        expected_key = shlex.quote("/path/to/key")
        expected_command = f"ssh -i {expected_key} -o StrictHostKeyChecking=accept-new"
        self.assertEqual(expected_command, env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path_with_spaces(self):
        git_source = GitSource(key_path="/path with spaces/to/key")
        env = git_source._build_git_env()

        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("'/path with spaces/to/key'", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_with_env(self, mock_repo_class):
        git_source = GitSource(key_path="/test/key")
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        result = git_source.clone_repo(
            "git@example.com:repo.git",
            "/local/path",
            mirror=False,
        )

        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/local/path", call_args[0][1])
        self.assertIn("env", call_args[1])
        self.assertEqual(result, mock_repo)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_mirror_option(self, mock_repo_class):
        git_source = GitSource(key_path="/test/key")
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source.clone_repo(
            "git@example.com:repo.git",
            "/local/mirror.git",
            mirror=True,
        )

        call_args = mock_repo_class.clone_from.call_args
        self.assertTrue(call_args[1].get("mirror"))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_failure(self, mock_repo_class):
        from git.exc import GitCommandError

        git_source = GitSource()
        mock_repo_class.clone_from.side_effect = GitCommandError(
            "git clone",
            128,
            stderr="error: could not clone",
        )

        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_object(self, mock_repo_class):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        result = git_source.open_repo("/existing/repo")

        mock_repo_class.assert_called_once_with("/existing/repo")
        self.assertEqual(result, mock_repo)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_invalid_repo(self, mock_repo_class):
        from git.exc import InvalidGitRepositoryError

        git_source = GitSource()
        mock_repo_class.side_effect = InvalidGitRepositoryError("/bad/path")

        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/bad/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/bad/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_no_such_path(self, mock_repo_class):
        from git.exc import NoSuchPathError

        git_source = GitSource()
        mock_repo_class.side_effect = NoSuchPathError("/nonexistent")

        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/nonexistent")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_remote_update_prune(self, mock_repo_class):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        result = git_source.update_mirror("/local/mirror.git")

        mock_repo.git.remote.assert_called_once_with("update", "--prune")
        self.assertEqual(result, mock_repo)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_repository_sync_error_on_failure(self, mock_repo_class):
        from git.exc import GitCommandError

        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_repo.git.remote.side_effect = GitCommandError(
            "git remote update",
            1,
            stderr="error: remote update failed",
        )

        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/local/mirror.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/local/mirror.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch(self, mock_repo_class):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin

        result = git_source.fetch_working_copy("/local/working")

        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertEqual(result, mock_repo)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_repository_sync_error_on_failure(self, mock_repo_class):
        from git.exc import GitCommandError

        git_source = GitSource()
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_origin.fetch.side_effect = GitCommandError(
            "git fetch",
            1,
            stderr="error: fetch failed",
        )

        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/local/working")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/local/working", str(context.exception))

    def test_checkout_branch_when_branch_exists_locally(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_head = Mock()
        mock_repo.heads = {"main": mock_head}

        git_source.checkout_branch(mock_repo, "main")

        mock_repo.git.checkout.assert_called_once_with("main")

    def test_checkout_branch_creates_new_local_branch_from_remote(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = {}

        git_source.checkout_branch(mock_repo, "feature-branch")

        mock_repo.git.checkout.assert_called_once_with("-B", "feature-branch", "origin/feature-branch")

    def test_checkout_branch_raises_repository_sync_error_on_failure(self):
        from git.exc import GitCommandError

        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = {}
        mock_repo.git.checkout.side_effect = GitCommandError(
            "git checkout",
            1,
            stderr="error: pathspec 'feature-branch' did not match",
        )

        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "feature-branch")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("feature-branch", str(context.exception))

    def test_checkout_branch_with_special_characters_in_name(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = {}

        git_source.checkout_branch(mock_repo, "feature/PROJ-123")

        mock_repo.git.checkout.assert_called_once_with("-B", "feature/PROJ-123", "origin/feature/PROJ-123")


if __name__ == "__main__":
    unittest.main()