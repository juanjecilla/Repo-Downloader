import os
import unittest
from unittest.mock import MagicMock, Mock, patch

try:
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
    from data.source.git_source import GitSource
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    GitCommandError = None
    InvalidGitRepositoryError = None
    NoSuchPathError = None
    GitSource = None
    GITPYTHON_AVAILABLE = False

from utils.errors import RepositorySyncError


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSource(unittest.TestCase):
    def test_init_expands_tilde_in_key_path(self):
        with patch("os.path.expanduser", return_value="/home/user/.ssh/id_rsa") as mock_expand:
            git_source = GitSource(key_path="~/.ssh/id_rsa")
            mock_expand.assert_called_once_with("~/.ssh/id_rsa")
            self.assertEqual("/home/user/.ssh/id_rsa", git_source._key_path)

    def test_init_uses_default_key_path(self):
        with patch("os.path.expanduser") as mock_expand:
            git_source = GitSource()
            mock_expand.assert_called_once_with("~/.ssh/id_rsa")

    def test_build_git_env_quotes_key_path(self):
        git_source = GitSource(key_path="/path/with spaces/id_rsa")
        env = git_source._build_git_env()
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("'/path/with spaces/id_rsa'", env["GIT_SSH_COMMAND"])
        self.assertIn("StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_build_git_env_includes_strict_host_key_checking(self):
        git_source = GitSource(key_path="/home/user/.ssh/id_rsa")
        env = git_source._build_git_env()
        self.assertIn("-o StrictHostKeyChecking=accept-new", env["GIT_SSH_COMMAND"])

    def test_clone_repo_passes_mirror_flag_when_true(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo.git", mirror=True)
            mock_repo.clone_from.assert_called_once()
            call_kwargs = mock_repo.clone_from.call_args[1]
            self.assertTrue(call_kwargs.get("mirror"))

    def test_clone_repo_does_not_pass_mirror_flag_when_false(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo", mirror=False)
            mock_repo.clone_from.assert_called_once()
            call_kwargs = mock_repo.clone_from.call_args[1]
            self.assertNotIn("mirror", call_kwargs)

    def test_clone_repo_wraps_git_command_error(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            mock_repo.clone_from.side_effect = GitCommandError("clone", 128, stderr="error")
            with self.assertRaises(RepositorySyncError) as context:
                git_source.clone_repo("git@example.com:repo.git", "/tmp/repo")
            self.assertIn("Failed cloning repository", str(context.exception))
            self.assertIn("git@example.com:repo.git", str(context.exception))

    def test_clone_repo_preserves_original_exception_as_cause(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            original_error = GitCommandError("clone", 128, stderr="permission denied")
            mock_repo.clone_from.side_effect = original_error
            with self.assertRaises(RepositorySyncError) as context:
                git_source.clone_repo("git@example.com:repo.git", "/tmp/repo")
            self.assertIsInstance(context.exception.__cause__, GitCommandError)

    def test_open_repo_returns_repo_object(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            mock_repo.return_value = Mock()
            result = git_source.open_repo("/tmp/repo")
            self.assertIsNotNone(result)
            mock_repo.assert_called_once_with("/tmp/repo")

    def test_open_repo_wraps_invalid_git_repository_error(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            mock_repo.side_effect = InvalidGitRepositoryError()
            with self.assertRaises(RepositorySyncError) as context:
                git_source.open_repo("/tmp/not-a-repo")
            self.assertIn("Invalid local repository path", str(context.exception))
            self.assertIn("/tmp/not-a-repo", str(context.exception))

    def test_open_repo_wraps_no_such_path_error(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            mock_repo.side_effect = NoSuchPathError()
            with self.assertRaises(RepositorySyncError) as context:
                git_source.open_repo("/tmp/missing")
            self.assertIn("Invalid local repository path", str(context.exception))

    def test_update_mirror_calls_remote_update_with_prune(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        with patch.object(git_source, "open_repo", return_value=mock_repo):
            result = git_source.update_mirror("/tmp/mirror.git")
            mock_git.remote.assert_called_once_with("update", "--prune")
            self.assertEqual(mock_repo, result)

    def test_update_mirror_wraps_git_command_error(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.remote.side_effect = GitCommandError("remote", 128, stderr="error")
        mock_repo.git = mock_git
        with patch.object(git_source, "open_repo", return_value=mock_repo):
            with self.assertRaises(RepositorySyncError) as context:
                git_source.update_mirror("/tmp/mirror.git")
            self.assertIn("Failed updating mirror repository", str(context.exception))
            self.assertIn("/tmp/mirror.git", str(context.exception))

    def test_fetch_working_copy_calls_origin_fetch_with_prune_and_tags(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        with patch.object(git_source, "open_repo", return_value=mock_repo):
            result = git_source.fetch_working_copy("/tmp/working")
            mock_origin.fetch.assert_called_once_with(prune=True, tags=True)
            self.assertEqual(mock_repo, result)

    def test_fetch_working_copy_wraps_git_command_error(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError("fetch", 128, stderr="error")
        mock_repo.remotes.origin = mock_origin
        with patch.object(git_source, "open_repo", return_value=mock_repo):
            with self.assertRaises(RepositorySyncError) as context:
                git_source.fetch_working_copy("/tmp/working")
            self.assertIn("Failed fetching working repository", str(context.exception))
            self.assertIn("/tmp/working", str(context.exception))

    def test_checkout_branch_existing_local_branch(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = ["main", "dev"]
        mock_git = Mock()
        mock_repo.git = mock_git
        git_source.checkout_branch(mock_repo, "main")
        mock_git.checkout.assert_called_once_with("main")

    def test_checkout_branch_creates_new_branch_from_origin(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = ["main"]
        mock_git = Mock()
        mock_repo.git = mock_git
        git_source.checkout_branch(mock_repo, "feature")
        mock_git.checkout.assert_called_once_with("-B", "feature", "origin/feature")

    def test_checkout_branch_wraps_git_command_error(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = []
        mock_git = Mock()
        mock_git.checkout.side_effect = GitCommandError("checkout", 128, stderr="error")
        mock_repo.git = mock_git
        with self.assertRaises(RepositorySyncError) as context:
            git_source.checkout_branch(mock_repo, "missing-branch")
        self.assertIn("Failed checking out branch", str(context.exception))
        self.assertIn("missing-branch", str(context.exception))

    def test_clone_repo_passes_git_env_to_clone_from(self):
        git_source = GitSource(key_path="/custom/key")
        with patch("data.source.git_source.Repo") as mock_repo:
            git_source.clone_repo("git@example.com:repo.git", "/tmp/repo")
            call_kwargs = mock_repo.clone_from.call_args[1]
            self.assertIn("env", call_kwargs)
            self.assertIn("GIT_SSH_COMMAND", call_kwargs["env"])


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for GitSource tests")
class TestGitSourceEdgeCases(unittest.TestCase):
    def test_clone_repo_with_special_characters_in_url(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            git_source.clone_repo("git@example.com:user/repo-with-dashes_and_underscores.git", "/tmp/repo")
            mock_repo.clone_from.assert_called_once()

    def test_open_repo_with_relative_path(self):
        git_source = GitSource()
        with patch("data.source.git_source.Repo") as mock_repo:
            git_source.open_repo("./relative/path")
            mock_repo.assert_called_once_with("./relative/path")

    def test_checkout_branch_with_slash_in_name(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = []
        mock_git = Mock()
        mock_repo.git = mock_git
        git_source.checkout_branch(mock_repo, "feature/new-feature")
        mock_git.checkout.assert_called_once_with("-B", "feature/new-feature", "origin/feature/new-feature")

    def test_update_mirror_returns_repo_object(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        with patch.object(git_source, "open_repo", return_value=mock_repo):
            result = git_source.update_mirror("/tmp/mirror.git")
            self.assertIs(result, mock_repo)

    def test_fetch_working_copy_returns_repo_object(self):
        git_source = GitSource()
        mock_repo = Mock()
        mock_origin = Mock()
        mock_repo.remotes.origin = mock_origin
        with patch.object(git_source, "open_repo", return_value=mock_repo):
            result = git_source.fetch_working_copy("/tmp/working")
            self.assertIs(result, mock_repo)


if __name__ == "__main__":
    unittest.main()