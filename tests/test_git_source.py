import os
import shlex
import unittest
from unittest.mock import MagicMock, Mock, patch

try:
    from git import Repo
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

    from data.source.git_source import GitSource
    from utils.errors import RepositorySyncError

    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    Repo = None
    GitSource = None
    RepositorySyncError = None
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceInit(unittest.TestCase):
    def test_git_source_accepts_default_key_path(self):
        source = GitSource()
        self.assertEqual(os.path.expanduser("~/.ssh/id_rsa"), source._key_path)

    def test_git_source_accepts_custom_key_path(self):
        source = GitSource(key_path="/custom/path/id_ed25519")
        self.assertEqual("/custom/path/id_ed25519", source._key_path)

    def test_git_source_expands_tilde_in_key_path(self):
        source = GitSource(key_path="~/.ssh/custom_key")
        expected = os.path.expanduser("~/.ssh/custom_key")
        self.assertEqual(expected, source._key_path)


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceBuildGitEnv(unittest.TestCase):
    def test_build_git_env_returns_dict_with_git_ssh_command(self):
        source = GitSource(key_path="/path/to/key")
        env = source._build_git_env()
        self.assertIsInstance(env, dict)
        self.assertIn("GIT_SSH_COMMAND", env)

    def test_build_git_env_includes_ssh_key_path(self):
        source = GitSource(key_path="/path/to/key")
        env = source._build_git_env()
        self.assertIn("/path/to/key", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        source = GitSource(key_path="/path with spaces/key")
        env = source._build_git_env()
        quoted_path = shlex.quote("/path with spaces/key")
        self.assertIn(quoted_path, env["GIT_SSH_COMMAND"])

    def test_build_git_env_includes_strict_host_key_checking(self):
        source = GitSource(key_path="/path/to/key")
        env = source._build_git_env()
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_starts_with_ssh_command(self):
        source = GitSource(key_path="/path/to/key")
        env = source._build_git_env()
        self.assertTrue(env["GIT_SSH_COMMAND"].startswith("ssh -i "))


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceCloneRepo(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_repo_clone_from(self, mock_repo_class):
        source = GitSource(key_path="/path/to/key")
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        result = source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        mock_repo_class.clone_from.assert_called_once()
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_passes_repository_url(self, mock_repo_class):
        source = GitSource()
        source.clone_repo("git@example.com:acme/repo.git", "/local/path", mirror=False)

        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:acme/repo.git", call_args[0][0])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_passes_local_path(self, mock_repo_class):
        source = GitSource()
        source.clone_repo("git@example.com:repo.git", "/local/path/repo", mirror=False)

        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("/local/path/repo", call_args[0][1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_passes_git_env(self, mock_repo_class):
        source = GitSource(key_path="/custom/key")
        source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        call_args = mock_repo_class.clone_from.call_args
        env = call_args[1]["env"]
        self.assertIn("GIT_SSH_COMMAND", env)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_passes_mirror_flag_when_true(self, mock_repo_class):
        source = GitSource()
        source.clone_repo("git@example.com:repo.git", "/local/path.git", mirror=True)

        call_args = mock_repo_class.clone_from.call_args
        self.assertTrue(call_args[1].get("mirror"))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_does_not_pass_mirror_flag_when_false(self, mock_repo_class):
        source = GitSource()
        source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        call_args = mock_repo_class.clone_from.call_args
        self.assertNotIn("mirror", call_args[1])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_command_error(self, mock_repo_class):
        source = GitSource()
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", "failed")

        with self.assertRaises(RepositorySyncError) as context:
            source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_chains_git_command_error(self, mock_repo_class):
        source = GitSource()
        original_error = GitCommandError("clone", "network error")
        mock_repo_class.clone_from.side_effect = original_error

        with self.assertRaises(RepositorySyncError) as context:
            source.clone_repo("git@example.com:repo.git", "/local/path", mirror=False)

        self.assertIsInstance(context.exception.__cause__, GitCommandError)


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceOpenRepo(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_open_repo_calls_repo_constructor(self, mock_repo_class):
        source = GitSource()
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        result = source.open_repo("/local/path")

        mock_repo_class.assert_called_once_with("/local/path")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_invalid_git_repository(
        self, mock_repo_class
    ):
        source = GitSource()
        mock_repo_class.side_effect = InvalidGitRepositoryError("/local/path")

        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/local/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/local/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_no_such_path(self, mock_repo_class):
        source = GitSource()
        mock_repo_class.side_effect = NoSuchPathError("/nonexistent/path")

        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/nonexistent/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/nonexistent/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_chains_original_exception(self, mock_repo_class):
        source = GitSource()
        original_error = InvalidGitRepositoryError("/local/path")
        mock_repo_class.side_effect = original_error

        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/local/path")

        self.assertIsInstance(context.exception.__cause__, InvalidGitRepositoryError)


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceUpdateMirror(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_update_mirror_opens_repository(self, mock_repo_class):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        source.update_mirror("/local/path.git")

        mock_repo_class.assert_called_once_with("/local/path.git")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_git_remote_update_prune(self, mock_repo_class):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        source.update_mirror("/local/path.git")

        mock_repo.git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_returns_repo_object(self, mock_repo_class):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        result = source.update_mirror("/local/path.git")

        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_repository_sync_error_on_git_command_error(
        self, mock_repo_class
    ):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", "update failed")
        mock_repo_class.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as context:
            source.update_mirror("/local/path.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/local/path.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_chains_git_command_error(self, mock_repo_class):
        source = GitSource()
        mock_repo = MagicMock()
        original_error = GitCommandError("remote", "update failed")
        mock_repo.git.remote.side_effect = original_error
        mock_repo_class.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as context:
            source.update_mirror("/local/path.git")

        self.assertIsInstance(context.exception.__cause__, GitCommandError)


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceFetchWorkingCopy(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_opens_repository(self, mock_repo_class):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        source.fetch_working_copy("/local/path")

        mock_repo_class.assert_called_once_with("/local/path")

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch_with_prune_and_tags(self, mock_repo_class):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        source.fetch_working_copy("/local/path")

        mock_repo.remotes.origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_returns_repo_object(self, mock_repo_class):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        result = source.fetch_working_copy("/local/path")

        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_repository_sync_error_on_git_command_error(
        self, mock_repo_class
    ):
        source = GitSource()
        mock_repo = MagicMock()
        mock_repo.remotes.origin.fetch.side_effect = GitCommandError("fetch", "network error")
        mock_repo_class.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as context:
            source.fetch_working_copy("/local/path")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/local/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_chains_git_command_error(self, mock_repo_class):
        source = GitSource()
        mock_repo = MagicMock()
        original_error = GitCommandError("fetch", "network error")
        mock_repo.remotes.origin.fetch.side_effect = original_error
        mock_repo_class.return_value = mock_repo

        with self.assertRaises(RepositorySyncError) as context:
            source.fetch_working_copy("/local/path")

        self.assertIsInstance(context.exception.__cause__, GitCommandError)


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceCheckoutBranch(unittest.TestCase):
    def test_checkout_branch_when_branch_exists_locally(self):
        mock_repo = MagicMock()
        mock_repo.heads = ["main", "dev", "feature"]
        source = GitSource()

        source.checkout_branch(mock_repo, "main")

        mock_repo.git.checkout.assert_called_once_with("main")

    def test_checkout_branch_when_branch_does_not_exist_locally(self):
        mock_repo = MagicMock()
        mock_repo.heads = ["main"]
        source = GitSource()

        source.checkout_branch(mock_repo, "dev")

        mock_repo.git.checkout.assert_called_once_with("-B", "dev", "origin/dev")

    def test_checkout_branch_raises_repository_sync_error_on_git_command_error(self):
        mock_repo = MagicMock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", "branch not found")
        source = GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            source.checkout_branch(mock_repo, "nonexistent")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("nonexistent", str(context.exception))

    def test_checkout_branch_chains_git_command_error(self):
        mock_repo = MagicMock()
        mock_repo.heads = []
        original_error = GitCommandError("checkout", "branch not found")
        mock_repo.git.checkout.side_effect = original_error
        source = GitSource()

        with self.assertRaises(RepositorySyncError) as context:
            source.checkout_branch(mock_repo, "nonexistent")

        self.assertIsInstance(context.exception.__cause__, GitCommandError)

    def test_checkout_branch_creates_tracking_branch_for_remote_branch(self):
        mock_repo = MagicMock()
        mock_repo.heads = []
        source = GitSource()

        source.checkout_branch(mock_repo, "release/1.0")

        mock_repo.git.checkout.assert_called_once_with("-B", "release/1.0", "origin/release/1.0")


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceEdgeCases(unittest.TestCase):
    def test_git_source_handles_empty_key_path(self):
        source = GitSource(key_path="")
        env = source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)

    def test_git_source_handles_special_characters_in_key_path(self):
        source = GitSource(key_path="/path/with'quote/key")
        env = source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_empty_url_raises_error(self, mock_repo_class):
        source = GitSource()
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", "invalid url")

        with self.assertRaises(RepositorySyncError):
            source.clone_repo("", "/local/path", mirror=False)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_none_local_path_raises_error(self, mock_repo_class):
        source = GitSource()
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", "invalid path")

        with self.assertRaises(RepositorySyncError):
            source.clone_repo("git@example.com:repo.git", None, mirror=False)


if __name__ == "__main__":
    unittest.main()