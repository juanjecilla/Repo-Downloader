import unittest
from unittest.mock import MagicMock, patch

from git.exc import GitCommandError, InvalidGitRepositoryError

from data.source.git_source import GitSource
from utils.errors import RepositorySyncError


class TestGitSourceClone(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_clone_repo_happy_path(self, repo_cls):
        fake_repo = MagicMock()
        repo_cls.clone_from.return_value = fake_repo

        source = GitSource()
        result = source.clone_repo("git@github.com:org/repo.git", "/tmp/repo")

        repo_cls.clone_from.assert_called_once()
        _, kwargs = repo_cls.clone_from.call_args
        self.assertIn("GIT_SSH_COMMAND", kwargs["env"])
        self.assertIs(fake_repo, result)

    @patch("data.source.git_source.Repo")
    def test_clone_repo_with_mirror_flag(self, repo_cls):
        repo_cls.clone_from.return_value = MagicMock()

        source = GitSource()
        source.clone_repo("git@github.com:org/repo.git", "/tmp/repo.git", mirror=True)

        _, kwargs = repo_cls.clone_from.call_args
        self.assertTrue(kwargs.get("mirror"))

    @patch("data.source.git_source.Repo")
    def test_clone_repo_raises_sync_error_on_failure(self, repo_cls):
        repo_cls.clone_from.side_effect = GitCommandError("clone", 128, "stderr")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            source.clone_repo("git@github.com:org/repo.git", "/tmp/repo")

        self.assertIn("Failed cloning", str(ctx.exception))

    def test_build_git_env_includes_ssh_command(self):
        source = GitSource(key_path="~/.ssh/custom_rsa")
        env = source._build_git_env()  # noqa: SLF001
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn("StrictHostKeyChecking", env["GIT_SSH_COMMAND"])


class TestGitSourceOpenRepo(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_open_repo_happy_path(self, repo_cls):
        fake_repo = MagicMock()
        repo_cls.return_value = fake_repo

        source = GitSource()
        result = source.open_repo("/tmp/existing_repo")

        repo_cls.assert_called_once_with("/tmp/existing_repo")
        self.assertIs(fake_repo, result)

    @patch("data.source.git_source.Repo")
    def test_open_repo_raises_sync_error_for_invalid_path(self, repo_cls):
        repo_cls.side_effect = InvalidGitRepositoryError("/tmp/not_a_repo")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            source.open_repo("/tmp/not_a_repo")

        self.assertIn("Invalid local repository path", str(ctx.exception))


class TestGitSourceUpdateMirror(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_update_mirror_happy_path(self, repo_cls):
        fake_repo = MagicMock()
        repo_cls.return_value = fake_repo

        source = GitSource()
        result = source.update_mirror("/tmp/repo.git")

        fake_repo.git.remote.assert_called_once_with("update", "--prune")
        self.assertIs(fake_repo, result)

    @patch("data.source.git_source.Repo")
    def test_update_mirror_raises_on_command_error(self, repo_cls):
        fake_repo = MagicMock()
        repo_cls.return_value = fake_repo
        fake_repo.git.remote.side_effect = GitCommandError("remote update", 1, "err")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            source.update_mirror("/tmp/repo.git")

        self.assertIn("Failed updating mirror", str(ctx.exception))


class TestGitSourceFetchWorkingCopy(unittest.TestCase):
    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_happy_path(self, repo_cls):
        fake_repo = MagicMock()
        repo_cls.return_value = fake_repo

        source = GitSource()
        result = source.fetch_working_copy("/tmp/repo")

        fake_repo.remotes.origin.fetch.assert_called_once_with(prune=True, tags=True)
        self.assertIs(fake_repo, result)

    @patch("data.source.git_source.Repo")
    def test_fetch_working_copy_raises_on_command_error(self, repo_cls):
        fake_repo = MagicMock()
        repo_cls.return_value = fake_repo
        fake_repo.remotes.origin.fetch.side_effect = GitCommandError("fetch", 1, "err")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            source.fetch_working_copy("/tmp/repo")

        self.assertIn("Failed fetching", str(ctx.exception))


class TestGitSourceCheckoutBranch(unittest.TestCase):
    def test_checkout_branch_uses_local_head_if_exists(self):
        fake_repo = MagicMock()
        fake_repo.heads = ["main", "feature/x"]

        source = GitSource()
        source.checkout_branch(fake_repo, "main")

        fake_repo.git.checkout.assert_called_once_with("main")

    def test_checkout_branch_creates_tracking_branch_if_not_local(self):
        fake_repo = MagicMock()
        fake_repo.heads = []

        source = GitSource()
        source.checkout_branch(fake_repo, "develop")

        fake_repo.git.checkout.assert_called_once_with("-B", "develop", "origin/develop")

    def test_checkout_branch_raises_sync_error_on_failure(self):
        fake_repo = MagicMock()
        fake_repo.heads = ["main"]
        fake_repo.git.checkout.side_effect = GitCommandError("checkout", 1, "err")

        source = GitSource()
        with self.assertRaises(RepositorySyncError) as ctx:
            source.checkout_branch(fake_repo, "main")

        self.assertIn("Failed checking out branch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
