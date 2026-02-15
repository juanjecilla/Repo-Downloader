import os
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
    def test_init_with_default_key_path(self):
        """Verify GitSource initializes with default SSH key path."""
        source = GitSource()
        self.assertTrue(source._key_path.endswith("id_rsa"))
        self.assertFalse(source._key_path.startswith("~"))

    def test_init_with_custom_key_path(self):
        """Verify GitSource initializes with custom SSH key path."""
        source = GitSource(key_path="~/.ssh/custom_key")
        self.assertTrue(source._key_path.endswith("custom_key"))
        self.assertFalse(source._key_path.startswith("~"))

    def test_build_git_env_constructs_ssh_command(self):
        """Verify _build_git_env creates proper SSH command environment."""
        source = GitSource(key_path="/path/to/key")
        env = source._build_git_env()

        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])
        self.assertIn("/path/to/key", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path_with_spaces(self):
        """Verify _build_git_env quotes key paths containing spaces."""
        source = GitSource(key_path="/path/with spaces/key")
        env = source._build_git_env()

        ssh_command = env["GIT_SSH_COMMAND"]
        self.assertIn("'", ssh_command)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_with_env(self, mock_repo_class):
        """Verify clone_repo passes SSH environment to git."""
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        source = GitSource(key_path="/test/key")
        result = source.clone_repo("git@example.com:repo.git", "/local/path")

        self.assertEqual(mock_repo, result)
        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@example.com:repo.git", call_args[0][0])
        self.assertEqual("/local/path", call_args[0][1])
        self.assertIn("env", call_args[1])
        self.assertIn("GIT_SSH_COMMAND", call_args[1]["env"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_mirror_flag(self, mock_repo_class):
        """Verify clone_repo passes mirror=True when requested."""
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        source = GitSource()
        source.clone_repo("git@example.com:repo.git", "/local/mirror.git", mirror=True)

        call_kwargs = mock_repo_class.clone_from.call_args[1]
        self.assertTrue(call_kwargs.get("mirror"))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_without_mirror_flag(self, mock_repo_class):
        """Verify clone_repo does not pass mirror flag when mirror=False."""
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        source = GitSource()
        source.clone_repo("git@example.com:repo.git", "/local/working", mirror=False)

        call_kwargs = mock_repo_class.clone_from.call_args[1]
        self.assertNotIn("mirror", call_kwargs)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_on_git_command_error(self, mock_repo_class):
        """Verify clone_repo raises RepositorySyncError on GitCommandError."""
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", "failed")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.clone_repo("git@example.com:repo.git", "/local/path")

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@example.com:repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_object(self, mock_repo_class):
        """Verify open_repo returns a Repo object for valid paths."""
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        result = source.open_repo("/path/to/repo")

        self.assertEqual(mock_repo, result)
        mock_repo_class.assert_called_once_with("/path/to/repo")

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_on_invalid_repository(self, mock_repo_class):
        """Verify open_repo raises RepositorySyncError on InvalidGitRepositoryError."""
        mock_repo_class.side_effect = InvalidGitRepositoryError("/bad/path")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/bad/path")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/bad/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_on_no_such_path(self, mock_repo_class):
        """Verify open_repo raises RepositorySyncError on NoSuchPathError."""
        mock_repo_class.side_effect = NoSuchPathError("/missing/path")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.open_repo("/missing/path")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_remote_update(self, mock_repo_class):
        """Verify update_mirror calls git remote update with prune."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        result = source.update_mirror("/mirror/path")

        self.assertEqual(mock_repo, result)
        mock_git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_on_git_command_error(self, mock_repo_class):
        """Verify update_mirror raises RepositorySyncError on GitCommandError."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("remote", "update failed")
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.update_mirror("/mirror/path")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/mirror/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch(self, mock_repo_class):
        """Verify fetch_working_copy calls origin.fetch with prune and tags."""
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        result = source.fetch_working_copy("/working/path")

        self.assertEqual(mock_repo, result)
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_on_git_command_error(self, mock_repo_class):
        """Verify fetch_working_copy raises RepositorySyncError on GitCommandError."""
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", "fetch failed")
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.fetch_working_copy("/working/path")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/working/path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_existing_local_branch(self, _mock_repo_class):
        """Verify checkout_branch checks out existing local branch."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_heads = ["main", "dev"]
        mock_repo.heads = mock_heads
        mock_repo.git = mock_git

        source = GitSource()
        source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_tracking_branch(self, _mock_repo_class):
        """Verify checkout_branch creates tracking branch for remote branches."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.heads = []
        mock_repo.git = mock_git

        source = GitSource()
        source.checkout_branch(mock_repo, "feature")

        mock_git.checkout.assert_called_once_with("-B", "feature", "origin/feature")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_on_git_command_error(self, _mock_repo_class):
        """Verify checkout_branch raises RepositorySyncError on GitCommandError."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError("checkout", "checkout failed")
        mock_repo.heads = []
        mock_repo.git = mock_git

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            source.checkout_branch(mock_repo, "broken")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("broken", str(context.exception))


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSourceEdgeCases(unittest.TestCase):
    def test_key_path_expansion_with_tilde(self):
        """Verify key path with tilde is expanded to absolute path."""
        source = GitSource(key_path="~/custom/key")
        self.assertFalse(source._key_path.startswith("~"))
        self.assertTrue(os.path.isabs(source._key_path))

    def test_key_path_with_environment_variables(self):
        """Verify key path handles environment variable expansion."""
        with patch.dict(os.environ, {"HOME": "/home/testuser"}):
            source = GitSource(key_path="~/test_key")
            self.assertIn("/home/testuser", source._key_path)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_special_characters_in_url(self, mock_repo_class):
        """Verify clone_repo handles URLs with special characters."""
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        source = GitSource()
        url = "git@example.com:user/repo-with-special_chars.git"
        source.clone_repo(url, "/local/path")

        call_args = mock_repo_class.clone_from.call_args[0]
        self.assertEqual(url, call_args[0])

    @patch("data.source.git_source.Repo")
    def test_open_repo_with_relative_path(self, mock_repo_class):
        """Verify open_repo works with relative paths."""
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        source.open_repo("./relative/path")

        mock_repo_class.assert_called_once_with("./relative/path")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_with_slash_in_name(self, _mock_repo_class):
        """Verify checkout_branch handles branch names with slashes."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.heads = []
        mock_repo.git = mock_git

        source = GitSource()
        source.checkout_branch(mock_repo, "feature/new-feature")

        mock_git.checkout.assert_called_once_with("-B", "feature/new-feature", "origin/feature/new-feature")

    @patch("data.source.git_source.Repo")
    def test_exception_chaining_preserves_original_error(self, mock_repo_class):
        """Verify exception chaining preserves original GitPython errors."""
        original_error = GitCommandError("clone", "authentication failed")
        mock_repo_class.clone_from.side_effect = original_error

        source = GitSource()
        try:
            source.clone_repo("git@example.com:repo.git", "/local/path")
            self.fail("Expected RepositorySyncError to be raised")
        except RepositorySyncError as exc:
            self.assertIsInstance(exc.__cause__, GitCommandError)
            self.assertEqual(original_error, exc.__cause__)

    @patch("data.source.git_source.Repo")
    def test_multiple_update_mirror_calls_idempotent(self, mock_repo_class):
        """Verify update_mirror can be called multiple times safely."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        source = GitSource()
        source.update_mirror("/mirror/path")
        source.update_mirror("/mirror/path")

        self.assertEqual(2, mock_git.remote.call_count)


if __name__ == "__main__":
    unittest.main()