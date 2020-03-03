from threading import Thread


class GitSource(Thread):
    def __init__(self, username, password):
        super().__init__()
        self._username = username
        self._password = password

    def clone_repo(self, url):
        pass
