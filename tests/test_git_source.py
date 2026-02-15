import importlib.util
import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from utils.errors import RepositorySyncError


GITPYTHON_AVAILABLE = importlib.util.find_spec("git") is not None
if GITPYTHON_AVAILABLE:
    from data.source.git_source import GitSource
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
else:
    GitSource = None


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git source tests")
class TestGitSource(unittest.TestCase):
    def test_git_source_initializes_with_default_key_path(self):
        git_source = GitSource()
        expected_path = os.path.expanduser("~/.ssh/id_rsa")
        self.assertEqual(expected_path, git_source._key_path)

    def test_git_source_initializes_with_custom_key_path(self):
        git_source = GitSource(key_path="~/.ssh/custom_key")
        expected_path = os.path.expanduser("~/.ssh/custom_key")
        self.assertEqual(expected_path, git_source._key_path)

    def test_git_source_expands_tilde_in_key_path(self):
        git_source = GitSource(key_path="~/my_keys/id_ed25519")
        self.assertNotIn("~", git_source._key_path)
        self.assertTrue(git_source._key_path.startswith("/"))

    def test_build_git_env_includes_ssh_command(self):
        git_source = GitSource(key_path="/home/user/.ssh/id_rsa")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_quotes_key_path_with_spaces(self):
        git_source = GitSource(key_path="/home/user/my keys/id_rsa")
        env = git_source._build_git_env()
        # shlex.quote should add quotes around paths with spaces
        self.assertIn("GIT_SSH_COMMAND", env)
        # The path should be properly quoted in the command
        self.assertIn("ssh -i", env["GIT_SSH_COMMAND"])

    @patch("data.source.git_source.Repo")
    def test_clone_repo_calls_repo_clone_from_with_env(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource(key_path="/home/user/.ssh/id_rsa")
        result = git_source.clone_repo(
            "git@github.com:example/repo.git",
            "/tmp/repo",
            mirror=False,
        )

        mock_repo_class.clone_from.assert_called_once()
        call_args = mock_repo_class.clone_from.call_args
        self.assertEqual("git@github.com:example/repo.git", call_args[0][0])
        self.assertEqual("/tmp/repo", call_args[0][1])
        self.assertIn("env", call_args[1])
        self.assertIn("GIT_SSH_COMMAND", call_args[1]["env"])
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_passes_mirror_flag_when_true(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource()
        git_source.clone_repo("git@github.com:example/repo.git", "/tmp/repo.git", mirror=True)

        call_kwargs = mock_repo_class.clone_from.call_args[1]
        self.assertTrue(call_kwargs.get("mirror"))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_does_not_pass_mirror_flag_when_false(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        git_source = GitSource()
        git_source.clone_repo("git@github.com:example/repo.git", "/tmp/repo", mirror=False)

        call_kwargs = mock_repo_class.clone_from.call_args[1]
        self.assertNotIn("mirror", call_kwargs)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_repository_sync_error_on_git_command_error(self, mock_repo_class):
        mock_repo_class.clone_from.side_effect = GitCommandError(
            "git clone", 128, stderr="fatal: repository not found"
        )

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.clone_repo("git@github.com:invalid/repo.git", "/tmp/repo")

        self.assertIn("Failed cloning repository", str(context.exception))
        self.assertIn("git@github.com:invalid/repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_returns_repo_instance(self, mock_repo_class):
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.open_repo("/tmp/existing-repo")

        mock_repo_class.assert_called_once_with("/tmp/existing-repo")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_invalid_git_repository(
        self, mock_repo_class
    ):
        mock_repo_class.side_effect = InvalidGitRepositoryError("/tmp/not-a-repo")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/tmp/not-a-repo")

        self.assertIn("Invalid local repository path", str(context.exception))
        self.assertIn("/tmp/not-a-repo", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_repository_sync_error_on_no_such_path(self, mock_repo_class):
        mock_repo_class.side_effect = NoSuchPathError("/tmp/nonexistent")

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.open_repo("/tmp/nonexistent")

        self.assertIn("Invalid local repository path", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_update_mirror_calls_git_remote_update_with_prune(self, mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.update_mirror("/tmp/repo.git")

        mock_git.remote.assert_called_once_with("update", "--prune")
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_repository_sync_error_on_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("git remote update", 1, stderr="error")
        mock_repo.git = mock_git
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.update_mirror("/tmp/repo.git")

        self.assertIn("Failed updating mirror repository", str(context.exception))
        self.assertIn("/tmp/repo.git", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_calls_origin_fetch_with_flags(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        result = git_source.fetch_working_copy("/tmp/working-repo")

        mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertEqual(mock_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_repository_sync_error_on_failure(self, mock_repo_class):
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError(
            "git fetch", 128, stderr="fatal: unable to access"
        )
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.fetch_working_copy("/tmp/working-repo")

        self.assertIn("Failed fetching working repository", str(context.exception))
        self.assertIn("/tmp/working-repo", str(context.exception))

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_checks_out_existing_local_branch(self, _mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev", "feature"]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "main")

        mock_git.checkout.assert_called_once_with("main")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_creates_tracking_branch_when_not_local(self, _mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = ["main"]
        mock_git = Mock()
        mock_repo.git = mock_git

        git_source = GitSource()
        git_source.checkout_branch(mock_repo, "feature-branch")

        mock_git.checkout.assert_called_once_with("-B", "feature-branch", "origin/feature-branch")

    @patch("data.source.git_source.Repo")
    def test_checkout_branch_raises_repository_sync_error_on_failure(self, _mock_repo_class):
        mock_repo = Mock()
        mock_repo.heads = []
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError(
            "git checkout", 1, stderr="error: pathspec 'invalid' did not match"
        )
        mock_repo.git = mock_git

        git_source = GitSource()
        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "invalid-branch")

        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("invalid-branch", str(context.exception))

    def test_git_source_preserves_exception_chain(self):
        with patch("data.source.git_source.Repo") as mock_repo_class:
            original_error = GitCommandError("git clone", 128, stderr="fatal")
            mock_repo_class.clone_from.side_effect = original_error

            git_source = GitSource()
            try:
                git_source.clone_repo("git@example.com:repo.git", "/tmp/repo")
            except RepositorySyncError as exc:
                self.assertIsNotNone(exc.__cause__)
                self.assertIsInstance(exc.__cause__, GitCommandError)


if __name__ == "__main__":
    unittest.main()