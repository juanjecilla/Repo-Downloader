import os
import tempfile
import unittest

try:
    from git import Repo
    from data.source.git_source import GitSource
    GITPYTHON_AVAILABLE = True
except ModuleNotFoundError:
    Repo = None
    GitSource = None
    GITPYTHON_AVAILABLE = False


@unittest.skipUnless(GITPYTHON_AVAILABLE, "GitPython is required for git integration tests")
class TestGitSourceIntegration(unittest.TestCase):
    def _configure_user(self, repo):
        with repo.config_writer() as config:
            config.set_value("user", "name", "Repo Downloader Test")
            config.set_value("user", "email", "repo-downloader-test@example.com")

    def _write_and_commit(self, repo, filename, content, message):
        file_path = os.path.join(repo.working_tree_dir, filename)
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        repo.index.add([filename])
        repo.index.commit(message)

    def _build_remote_with_source(self, root_dir):
        source_path = os.path.join(root_dir, "source")
        source_repo = Repo.init(source_path)
        self._configure_user(source_repo)
        self._write_and_commit(source_repo, "README.md", "v1\n", "initial commit")
        branch = source_repo.active_branch.name

        remote_path = os.path.join(root_dir, "remote.git")
        Repo.clone_from(source_path, remote_path, bare=True)
        source_repo.create_remote("origin", remote_path)
        source_repo.git.push("--set-upstream", "origin", branch)
        return source_repo, remote_path, branch

    def test_mirror_clone_and_update_from_local_remote(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, branch = self._build_remote_with_source(tmp_dir)

            git_source = GitSource()
            mirror_path = os.path.join(tmp_dir, "mirror.git")
            mirror_repo = git_source.clone_repo(remote_path, mirror_path, mirror=True)
            self.assertTrue(mirror_repo.bare)

            self._write_and_commit(source_repo, "README.md", "v2\n", "second commit")
            source_repo.git.push("origin", branch)

            git_source.update_mirror(mirror_path)

            remote_sha = Repo(remote_path).git.rev_parse(branch)
            mirror_sha = Repo(mirror_path).git.rev_parse(branch)
            self.assertEqual(remote_sha, mirror_sha)

    def test_working_clone_fetch_updates_origin_tracking_branch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, branch = self._build_remote_with_source(tmp_dir)

            git_source = GitSource()
            working_path = os.path.join(tmp_dir, "working")
            git_source.clone_repo(remote_path, working_path, mirror=False)

            self._write_and_commit(source_repo, "README.md", "v2\n", "second commit")
            source_repo.git.push("origin", branch)

            updated_repo = git_source.fetch_working_copy(working_path)
            remote_sha = Repo(remote_path).git.rev_parse(branch)
            tracking_sha = updated_repo.git.rev_parse(f"origin/{branch}")
            self.assertEqual(remote_sha, tracking_sha)

    def test_open_repo_succeeds_for_valid_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = os.path.join(tmp_dir, "repo")
            Repo.init(repo_path)

            git_source = GitSource()
            repo = git_source.open_repo(repo_path)
            self.assertIsNotNone(repo)

    def test_open_repo_raises_for_invalid_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            invalid_path = os.path.join(tmp_dir, "not-a-repo")

            git_source = GitSource()
            with self.assertRaises(Exception) as ctx:
                git_source.open_repo(invalid_path)
            self.assertIn("Invalid local repository", str(ctx.exception))

    def test_open_repo_raises_for_nonexistent_path(self):
        git_source = GitSource()
        with self.assertRaises(Exception) as ctx:
            git_source.open_repo("/nonexistent/path/to/repo")
        self.assertIn("Invalid local repository", str(ctx.exception))

    def test_checkout_branch_creates_new_local_branch_from_remote(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, _ = self._build_remote_with_source(tmp_dir)

            # Create a new branch in the source repo
            source_repo.git.checkout("-b", "feature/new")
            self._write_and_commit(source_repo, "feature.txt", "feature content\n", "add feature")
            source_repo.git.push("--set-upstream", "origin", "feature/new")
            source_repo.git.checkout("main")

            # Clone and checkout the feature branch
            git_source = GitSource()
            working_path = os.path.join(tmp_dir, "working")
            repo = git_source.clone_repo(remote_path, working_path, mirror=False)

            git_source.checkout_branch(repo, "feature/new")
            self.assertEqual("feature/new", repo.active_branch.name)

    def test_checkout_branch_switches_to_existing_local_branch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, branch = self._build_remote_with_source(tmp_dir)

            # Create dev branch
            source_repo.git.checkout("-b", "dev")
            self._write_and_commit(source_repo, "dev.txt", "dev content\n", "add dev")
            source_repo.git.push("--set-upstream", "origin", "dev")

            # Clone and create local branches
            git_source = GitSource()
            working_path = os.path.join(tmp_dir, "working")
            repo = git_source.clone_repo(remote_path, working_path, mirror=False)

            # Checkout dev first time (creates local branch)
            git_source.checkout_branch(repo, "dev")
            self.assertEqual("dev", repo.active_branch.name)

            # Switch back to main
            git_source.checkout_branch(repo, branch)
            self.assertEqual(branch, repo.active_branch.name)

            # Switch to dev again (should use existing local branch)
            git_source.checkout_branch(repo, "dev")
            self.assertEqual("dev", repo.active_branch.name)

    def test_checkout_branch_raises_for_nonexistent_branch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, _ = self._build_remote_with_source(tmp_dir)

            git_source = GitSource()
            working_path = os.path.join(tmp_dir, "working")
            repo = git_source.clone_repo(remote_path, working_path, mirror=False)

            with self.assertRaises(Exception) as ctx:
                git_source.checkout_branch(repo, "nonexistent-branch")
            self.assertIn("Failed checking out branch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()