import json

import requests
from requests.auth import HTTPBasicAuth

from data.source.git_source import GitSource


class BitbucketSource(GitSource):
    BASE_API_URL = "https://api.bitbucket.org/2.0/"

    def __init__(self, username, password):
        super().__init__(username, password)
        self._current_user = self.get_user_info()

    def get_repo_list(self, workspace=None, paginated=False):
        url = self.BASE_API_URL + "repositories/"

        if workspace is None:
            url = url + self._username
        else:
            url = url + workspace

        return self._get_api_paginated_results(url, paginated)

    def get_user_info(self):
        url = self.BASE_API_URL + "user/"
        raw_request = requests.get(url, auth=HTTPBasicAuth(self._username, self._password))
        if raw_request.status_code == 200:
            dict_request = json.loads(raw_request.content.decode('utf-8'))
            return dict_request
        else:
            return None

    def _get_api_paginated_results(self, url, full_results):
        raw_request = requests.get(url, auth=HTTPBasicAuth(self._username, self._password))
        if raw_request.status_code == 200:
            dict_request = json.loads(raw_request.content.decode('utf-8'))
            values = dict_request['values']

            if full_results:
                if "next" in dict_request:
                    values.extend(self._get_api_paginated_results(dict_request["next"], full_results))

            return values
        else:
            return None

    def _get_api_result(self, url):
        raw_request = requests.get(url, auth=HTTPBasicAuth(self._username, self._password))
        if raw_request.status_code == 200:
            value = json.loads(raw_request.content.decode('utf-8'))
            return value
        else:
            return None

    def get_repositories_by_permission(self, role="member"):
        url = self.BASE_API_URL + "user/permissions/repositories?role={}".format(role)
        return self._get_api_paginated_results(url, True)

    def get_branches(self, name):
        url = self.BASE_API_URL + "repositories/{}/refs/branches".format(name)
        results = self._get_api_paginated_results(url, True)
        return results

    @property
    def current_user(self):
        return self._current_user

    def get_repository(self, workspace, name):
        url = self.BASE_API_URL + "repositories/{}/{}".format(workspace, name)
        return self._get_api_result(url)
