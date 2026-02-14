import os
import shlex
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from utils.errors import RepositorySyncError


class GitSource:
    def __init__(self, key_path="~/.ssh/id_rsa"):
        self._key_path = os.path.expanduser(key_path)

    def _build_git_env(self):
        key_path = shlex.quote(self._key_path)
        return {"GIT_SSH_COMMAND": f"ssh -i {key_path} -o StrictHostKeyChecking=accept-new"}

    def clone_repo(self, repo_url, local_path, mirror=False):
        try:
            clone_kwargs = {"env": self._build_git_env()}
            if mirror:
                clone_kwargs["mirror"] = True
            return Repo.clone_from(repo_url, local_path, **clone_kwargs)
        except GitCommandError as exc:
            raise RepositorySyncError(f"Failed cloning repository from {repo_url}: {exc}") from exc

    def open_repo(self, local_url):
        try:
            return Repo(local_url)
        except (InvalidGitRepositoryError, NoSuchPathError) as exc:
            raise RepositorySyncError(f"Invalid local repository path: {local_url}") from exc

    def update_mirror(self, local_path):
        repo = self.open_repo(local_path)
        try:
            repo.git.remote("update", "--prune")
            return repo
        except GitCommandError as exc:
            raise RepositorySyncError(
                f"Failed updating mirror repository at {local_path}: {exc}"
            ) from exc

    def fetch_working_copy(self, local_path):
        repo = self.open_repo(local_path)
        try:
            repo.remotes.origin.fetch(prune=True, tags=True)
            return repo
        except GitCommandError as exc:
            raise RepositorySyncError(
                f"Failed fetching working repository at {local_path}: {exc}"
            ) from exc

    def checkout_branch(self, repo, branch_name):
        try:
            if branch_name in repo.heads:
                repo.git.checkout(branch_name)
            else:
                repo.git.checkout("-B", branch_name, f"origin/{branch_name}")
        except GitCommandError as exc:
            raise RepositorySyncError(f"Failed checking out branch '{branch_name}': {exc}") from exc
