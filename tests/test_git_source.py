import os
import unittest
from unittest.mock import Mock, patch, MagicMock

from utils.errors import RepositorySyncError


try:
    from data.source.git_source import GitSource
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    GitSource = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_git_source_initializes_with_default_key_path(self):
        git_source = GitSource()
        self.assertIsNotNone(git_source._key_path)
        self.assertIn(".ssh/id_rsa", git_source._key_path)

    def test_git_source_initializes_with_custom_key_path(self):
        git_source = GitSource(key_path="/custom/path/id_ed25519")
        self.assertEqual("/custom/path/id_ed25519", git_source._key_path)

    def test_git_source_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        self.assertFalse(git_source._key_path.startswith("~"))
        self.assertTrue(os.path.isabs(git_source._key_path))

    def test_build_git_env_includes_ssh_command_with_key_path(self):
        git_source = GitSource(key_path="/path/to/key")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("/path/to/key", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path with spaces/key")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_clone_from_with_env(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo
        git_source = GitSource(key_path="/path/to/key")

        result = git_source.clone_repo(
            "git@github.com:acme/repo.git",
            "/local/path/repo",
            mirror=False,
        )

        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@github.com:acme/repo.git", call_args.args[0])
        self.assertEqual("/local/path/repo", call_args.args[1])
        self.assertIn("env", call_args.kwargs)
        self.assertIn("GIT_SSH_COMMAND", call_args.kwargs["env"])
        self.assertNotIn("mirror", call_args.kwargs)
        self.assertIs(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_includes_mirror_flag_when_requested(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo
        git_source = GitSource()

        result = git_source.clone_repo(
            "git@github.com:acme/repo.git",
            "/local/path/repo.git",
            mirror=True,
        )

        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertTrue(call_args.kwargs.get("mirror"))
        self.assertIs(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_sync_error_on_git_failure(self, mock_repo_class):
        from git.exc import GitCommandError

        mock_repo_class.clone_from.side_effect = GitCommandError("clone", 128)
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.clone_repo("git@github.com:acme/repo.git", "/local/path/repo", mirror=False)

        self.assertIn("Failed cloning repository", str(ctx.exception))
        self.assertIn("git@github.com:acme/repo.git", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_object(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        result = git_source.open_repo("/local/path/repo")

        mock_repo_class.assert_called_once_with("/local/path/repo")
        self.assertIs(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_on_invalid_repo(self, mock_repo_class):
        from git.exc import InvalidGitRepositoryError

        mock_repo_class.side_effect = InvalidGitRepositoryError("/local/path/repo")
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.open_repo("/local/path/repo")

        self.assertIn("Invalid local repository path", str(ctx.exception))
        self.assertIn("/local/path/repo", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_on_no_such_path(self, mock_repo_class):
        from git.exc import NoSuchPathError

        mock_repo_class.side_effect = NoSuchPathError("/local/path/repo")
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.open_repo("/local/path/repo")

        self.assertIn("Invalid local repository path", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_git_remote_update_with_prune(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.git = Mock()
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        result = git_source.update_mirror("/local/path/repo.git")

        mock_repo_class.assert_called_once_with("/local/path/repo.git")
        mock_repo.git.remote.assert_called_once_with("update", "--prune")
        self.assertIs(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_sync_error_on_git_failure(self, mock_repo_class):
        from git.exc import GitCommandError

        mock_repo = Mock()
        mock_repo.git.remote.side_effect = GitCommandError("remote", 128)
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.update_mirror("/local/path/repo.git")

        self.assertIn("Failed updating mirror repository", str(ctx.exception))
        self.assertIn("/local/path/repo.git", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch_with_prune_and_tags(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        result = git_source.fetch_working_copy("/local/path/repo")

        mock_repo_class.assert_called_once_with("/local/path/repo")
        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertIs(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_sync_error_on_git_failure(self, mock_repo_class):
        from git.exc import GitCommandError

        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", 128)
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.fetch_working_copy("/local/path/repo")

        self.assertIn("Failed fetching working repository", str(ctx.exception))
        self.assertIn("/local/path/repo", str(ctx.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_checks_out_existing_local_branch(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev"]
        mock_repo.git = Mock()
        git_source = GitSource()

        git_source.checkout_branch(mock_repo, "main")

        mock_repo.git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_tracking_branch_when_not_local(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main"]
        mock_repo.git = Mock()
        git_source = GitSource()

        git_source.checkout_branch(mock_repo, "dev")

        mock_repo.git.checkout.assert_called_once_with("-B", "dev", "origin/dev")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_sync_error_on_git_failure(self, mock_repo_class):
        from git.exc import GitCommandError

        mock_repo = Mock()
        mock_repo.heads = ["main"]
        mock_repo.git.checkout.side_effect = GitCommandError("checkout", 128)
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.checkout_branch(mock_repo, "dev")

        self.assertIn("Failed checking out branch", str(ctx.exception))
        self.assertIn("'dev'", str(ctx.exception))

    def test_git_source_env_isolates_ssh_config(self):
        git_source = GitSource(key_path="/custom/key")
        env = git_source._build_git_env()

        self.assertIn("ssh -i ", env["GIT_SSH_COMMAND"])
        self.assertIn("-o StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_empty_mirror_flag_defaults_to_false(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo
        git_source = GitSource()

        git_source.clone_repo("git@github.com:acme/repo.git", "/local/path/repo")

        call_args = mock_repo_class.clone_from.call_args
        self.assertNotIn("mirror", call_args.kwargs)

    @patch("data.source.git_source.Repo")
    def test_open_repo_with_nonexistent_path_raises_sync_error(self, mock_repo_class):
        from git.exc import NoSuchPathError

        mock_repo_class.side_effect = NoSuchPathError("/does/not/exist")
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError):
            git_source.open_repo("/does/not/exist")

    @patch("data.source.git_source.Repo")
    def test_update_mirror_with_bare_repo(self, mock_repo_class):
        mock_repo = MagicMock()
        mock_repo.bare = True
        mock_repo.git = Mock()
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        result = git_source.update_mirror("/local/path/repo.git")

        self.assertIs(mock_repo, result)
        mock_repo.git.remote.assert_called_once_with("update", "--prune")

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_with_no_origin_remote_raises_sync_error(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.remotes = Mock(spec=[])
        mock_repo_class.return_value = mock_repo
        git_source = GitSource()

        with self.assertRaises(AttributeError):
            git_source.fetch_working_copy("/local/path/repo")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_with_special_characters_in_name(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = []
        mock_repo.git = Mock()
        git_source = GitSource()

        git_source.checkout_branch(mock_repo, "feature/FOO-123-bar")

        mock_repo.git.checkout.assert_called_once_with(
            "-B", "feature/FOO-123-bar", "origin/feature/FOO-123-bar"
        )

    @patch("data.source.git_source.Repo")
    def test_clone_repo_wraps_git_errors_with_context(self, mock_repo_class):
        from git.exc import GitCommandError

        error_message = "fatal: repository does not exist"
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", 128, stderr=error_message)
        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.clone_repo(
                "git@github.com:nonexistent/repo.git",
                "/local/path",
                mirror=False,
            )

        self.assertIn("Failed cloning repository", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()