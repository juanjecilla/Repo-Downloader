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
    def _close_repo(self, repo):
        close = getattr(repo, "close", None)
        if callable(close):
            close()

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
            mirror_repo = None
            remote_repo = None
            mirror_verify_repo = None

            try:
                git_source = GitSource()
                mirror_path = os.path.join(tmp_dir, "mirror.git")
                mirror_repo = git_source.clone_repo(remote_path, mirror_path, mirror=True)
                self.assertTrue(mirror_repo.bare)

                self._write_and_commit(source_repo, "README.md", "v2\n", "second commit")
                source_repo.git.push("origin", branch)

                git_source.update_mirror(mirror_path)

                remote_repo = Repo(remote_path)
                mirror_verify_repo = Repo(mirror_path)
                remote_sha = remote_repo.git.rev_parse(branch)
                mirror_sha = mirror_verify_repo.git.rev_parse(branch)
                self.assertEqual(remote_sha, mirror_sha)
            finally:
                self._close_repo(source_repo)
                self._close_repo(mirror_repo)
                self._close_repo(remote_repo)
                self._close_repo(mirror_verify_repo)

    def test_working_clone_fetch_updates_origin_tracking_branch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_repo, remote_path, branch = self._build_remote_with_source(tmp_dir)
            working_repo = None
            updated_repo = None
            remote_repo = None

            try:
                git_source = GitSource()
                working_path = os.path.join(tmp_dir, "working")
                working_repo = git_source.clone_repo(remote_path, working_path, mirror=False)

                self._write_and_commit(source_repo, "README.md", "v2\n", "second commit")
                source_repo.git.push("origin", branch)

                updated_repo = git_source.fetch_working_copy(working_path)
                remote_repo = Repo(remote_path)
                remote_sha = remote_repo.git.rev_parse(branch)
                tracking_sha = updated_repo.git.rev_parse(f"origin/{branch}")
                self.assertEqual(remote_sha, tracking_sha)
            finally:
                self._close_repo(source_repo)
                self._close_repo(working_repo)
                self._close_repo(updated_repo)
                self._close_repo(remote_repo)


if __name__ == "__main__":
    unittest.main()
