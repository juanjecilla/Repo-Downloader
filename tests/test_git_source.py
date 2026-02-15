import os
import shlex
import tempfile
import unittest
from unittest.mock import Mock, patch

from utils.errors import RepositorySyncError


class TestGitSource(unittest.TestCase):
    def test_git_source_constructor_expands_key_path(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource(key_path="~/.ssh/custom_key")
        expanded_path = os.path.expanduser("~/.ssh/custom_key")
        self.assertEqual(expanded_path, git_source._key_path)

    def test_git_source_default_key_path(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()
        expanded_default = os.path.expanduser("~/.ssh/id_rsa")
        self.assertEqual(expanded_default, git_source._key_path)

    def test_build_git_env_includes_ssh_command(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource(key_path="/custom/path/key")
        env = git_source._build_git_env()

        self.assertIn("GIT_SSH_COMMAND", env)
        ssh_command = env["GIT_SSH_COMMAND"]
        self.assertIn("ssh", ssh_command)
        self.assertIn("-i", ssh_command)
        self.assertIn(shlex.quote("/custom/path/key"), ssh_command)
        self.assertIn("StrictHostKeyChecking=accept-new", ssh_command)

    def test_build_git_env_quotes_key_path_safely(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource(key_path="/path with spaces/id_rsa")
        env = git_source._build_git_env()

        ssh_command = env["GIT_SSH_COMMAND"]
        # shlex.quote should handle spaces correctly
        self.assertIn("ssh", ssh_command)
        self.assertIn("-i", ssh_command)

    def test_clone_repo_raises_repository_sync_error_on_git_failure(self):
        try:
            from data.source.git_source import GitSource
            import git.exc
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()

        with patch("data.source.git_source.Repo.clone_from") as mock_clone:
            mock_clone.side_effect = git.exc.GitCommandError("clone", 1, stderr="error")

            with self.assertRaises(RepositorySyncError) as ctx:
                git_source.clone_repo(
                    "git@example.com:acme/repo.git",
                    "/tmp/repo",
                    mirror=False,
                )

            self.assertIn("Failed cloning repository", str(ctx.exception))

    def test_clone_repo_passes_mirror_flag_to_git(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()

        with patch("data.source.git_source.Repo.clone_from") as mock_clone:
            mock_clone.return_value = Mock()
            git_source.clone_repo(
                "git@example.com:acme/repo.git",
                "/tmp/repo.git",
                mirror=True,
            )

            call_kwargs = mock_clone.call_args.kwargs
            self.assertTrue(call_kwargs.get("mirror"))
            self.assertIn("env", call_kwargs)

    def test_open_repo_raises_repository_sync_error_on_invalid_path(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.open_repo("/nonexistent/path")

        self.assertIn("Invalid local repository path", str(ctx.exception))

    def test_open_repo_raises_repository_sync_error_on_invalid_git_repo(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            git_source = GitSource()
            with self.assertRaises(RepositorySyncError):
                git_source.open_repo(tmp_dir)

    def test_update_mirror_raises_repository_sync_error_on_failure(self):
        try:
            from data.source.git_source import GitSource
            import git.exc
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()

        with patch.object(git_source, "open_repo") as mock_open:
            mock_repo = Mock()
            mock_repo.git.remote.side_effect = git.exc.GitCommandError("remote", 1, stderr="error")
            mock_open.return_value = mock_repo

            with self.assertRaises(RepositorySyncError) as ctx:
                git_source.update_mirror("/tmp/repo.git")

            self.assertIn("Failed updating mirror repository", str(ctx.exception))

    def test_update_mirror_calls_git_remote_update_with_prune(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()

        with patch.object(git_source, "open_repo") as mock_open:
            mock_repo = Mock()
            mock_open.return_value = mock_repo
            result = git_source.update_mirror("/tmp/repo.git")

            mock_repo.git.remote.assert_called_once_with("update", "--prune")
            self.assertEqual(mock_repo, result)

    def test_fetch_working_copy_raises_repository_sync_error_on_failure(self):
        try:
            from data.source.git_source import GitSource
            import git.exc
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()

        with patch.object(git_source, "open_repo") as mock_open:
            mock_repo = Mock()
            mock_repo.remotes.origin.fetch.side_effect = git.exc.GitCommandError(
                "fetch", 1, stderr="error"
            )
            mock_open.return_value = mock_repo

            with self.assertRaises(RepositorySyncError) as ctx:
                git_source.fetch_working_copy("/tmp/repo")

            self.assertIn("Failed fetching working repository", str(ctx.exception))

    def test_fetch_working_copy_fetches_with_prune_and_tags(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()

        with patch.object(git_source, "open_repo") as mock_open:
            mock_repo = Mock()
            mock_open.return_value = mock_repo
            result = git_source.fetch_working_copy("/tmp/repo")

            mock_repo.remotes.origin.fetch.assert_called_once_with(prune=True, tags=True)
            self.assertEqual(mock_repo, result)

    def test_checkout_branch_creates_new_branch_when_not_exists(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = []

        git_source.checkout_branch(mock_repo, "feature-branch")

        mock_repo.git.checkout.assert_called_once_with("-B", "feature-branch", "origin/feature-branch")

    def test_checkout_branch_switches_to_existing_branch(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = ["main", "feature-branch"]

        git_source.checkout_branch(mock_repo, "feature-branch")

        mock_repo.git.checkout.assert_called_once_with("feature-branch")

    def test_checkout_branch_raises_repository_sync_error_on_failure(self):
        try:
            from data.source.git_source import GitSource
            import git.exc
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource()
        mock_repo = Mock()
        mock_repo.heads = []
        mock_repo.git.checkout.side_effect = git.exc.GitCommandError("checkout", 1, stderr="error")

        with self.assertRaises(RepositorySyncError) as ctx:
            git_source.checkout_branch(mock_repo, "feature-branch")

        self.assertIn("Failed checking out branch", str(ctx.exception))
        self.assertIn("feature-branch", str(ctx.exception))

    def test_clone_repo_passes_env_to_git_command(self):
        try:
            from data.source.git_source import GitSource
        except ModuleNotFoundError:
            self.skipTest("GitPython not available")

        git_source = GitSource(key_path="/custom/key")

        with patch("data.source.git_source.Repo.clone_from") as mock_clone:
            mock_clone.return_value = Mock()
            git_source.clone_repo(
                "git@example.com:acme/repo.git",
                "/tmp/repo",
                mirror=False,
            )

            call_kwargs = mock_clone.call_args.kwargs
            self.assertIn("env", call_kwargs)
            env = call_kwargs["env"]
            self.assertIn("GIT_SSH_COMMAND", env)


if __name__ == "__main__":
    unittest.main()