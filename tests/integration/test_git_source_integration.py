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

    def test_checkout_branch_switches_to_existing_local_branch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, branch = self._build_remote_with_source(tmp_dir)

            git_source = GitSource()
            working_path = os.path.join(tmp_dir, "working")
            repo = git_source.clone_repo(remote_path, working_path, mirror=False)

            # Create and checkout a new branch locally
            source_repo.git.checkout("-b", "dev")
            self._write_and_commit(source_repo, "dev.txt", "dev content\n", "dev commit")
            source_repo.git.push("origin", "dev")

            # Fetch the new branch
            git_source.fetch_working_copy(working_path)

            # Checkout the new branch for the first time
            git_source.checkout_branch(repo, "dev")
            self.assertEqual("dev", repo.active_branch.name)

            # Switch back to original branch
            git_source.checkout_branch(repo, branch)
            self.assertEqual(branch, repo.active_branch.name)

            # Switch back to dev (should use existing local branch)
            git_source.checkout_branch(repo, "dev")
            self.assertEqual("dev", repo.active_branch.name)

    def test_checkout_branch_creates_tracking_branch_for_remote_only(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, branch = self._build_remote_with_source(tmp_dir)

            # Create a new branch on remote
            source_repo.git.checkout("-b", "feature")
            self._write_and_commit(source_repo, "feature.txt", "feature\n", "feature commit")
            source_repo.git.push("origin", "feature")
            source_repo.git.checkout(branch)

            git_source = GitSource()
            working_path = os.path.join(tmp_dir, "working")
            repo = git_source.clone_repo(remote_path, working_path, mirror=False)
            git_source.fetch_working_copy(working_path)

            # Checkout the remote-only branch
            git_source.checkout_branch(repo, "feature")
            self.assertEqual("feature", repo.active_branch.name)
            self.assertTrue(os.path.exists(os.path.join(working_path, "feature.txt")))

    def test_open_repo_on_non_bare_repository(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, _ = self._build_remote_with_source(tmp_dir)

            git_source = GitSource()
            opened_repo = git_source.open_repo(source_repo.working_tree_dir)

            self.assertEqual(source_repo.working_tree_dir, opened_repo.working_tree_dir)
            self.assertFalse(opened_repo.bare)

    def test_mirror_clone_creates_bare_repository(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, remote_path, _ = self._build_remote_with_source(tmp_dir)

            git_source = GitSource()
            mirror_path = os.path.join(tmp_dir, "test-mirror.git")
            mirror_repo = git_source.clone_repo(remote_path, mirror_path, mirror=True)

            self.assertTrue(mirror_repo.bare)
            self.assertIsNone(mirror_repo.working_tree_dir)


if __name__ == "__main__":
    unittest.main()