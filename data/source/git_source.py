from threading import Thread

from git import Repo


class GitSource(Thread):
    def __init__(self, username, password, key_path="~/.ssh/id_rsa"):
        super().__init__()
        self._username = username
        self._password = password
        self._key_path = key_path

    def clone_repo(self, repo_url, local_path="./repo/"):
        cloned_repo = Repo.clone_from(repo_url, local_path,
                                      env={'GIT_SSH_COMMAND': 'ssh -i {}'.format(self._key_path)})
        return cloned_repo

    def open_repo(self, local_url):
        local_repo = Repo(local_url)
        return local_repo
