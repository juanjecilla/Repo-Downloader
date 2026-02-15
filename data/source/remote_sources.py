from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry

from data.source.provider_interface import RemoteProvider
from utils.errors import AuthenticationError, ProviderNotImplementedError, RemoteAPIError
from utils.repo_utils import filter_repositories_by_workspace


class BitbucketSource(RemoteProvider):
    provider_name = "bitbucket"
    BASE_API_URL = "https://api.bitbucket.org/2.0/"

    def __init__(self, username, password, timeout=20, retries=3):
        self._username = username
        self._password = password
        self._timeout = timeout
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(self._username, self._password)

        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"GET"},
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)

        self._current_user = None
        self._auth_error = None
        try:
            self._current_user = self.get_user_info()
        except (AuthenticationError, RemoteAPIError) as exc:
            self._auth_error = str(exc)

    def _request_json(self, url):
        try:
            response = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as exc:
            raise RemoteAPIError(f"Request to '{url}' failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed for '{url}' "
                f"(status {response.status_code})"
            )
        if response.status_code >= 400:
            raise RemoteAPIError(f"Request to '{url}' failed with status {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise RemoteAPIError(f"Invalid JSON received from '{url}'") from exc

    def _get_paginated_results(self, url):
        values = []
        next_url = url

        while next_url:
            payload = self._request_json(next_url)
            page_values = payload.get("values")
            if page_values is None:
                raise RemoteAPIError(f"Paginated endpoint '{next_url}' did not include 'values'")
            values.extend(page_values)
            next_url = payload.get("next")

        return values

    def get_user_info(self):
        return self._request_json(self.BASE_API_URL + "user/")

    def list_repositories(self, workspace=None, role="member"):
        url = f"{self.BASE_API_URL}user/permissions/repositories?role={role}"
        repositories = self._get_paginated_results(url)
        return filter_repositories_by_workspace(repositories, workspace)

    def list_branches(self, full_name):
        url = f"{self.BASE_API_URL}repositories/{full_name}/refs/branches"
        return self._get_paginated_results(url)

    @property
    def current_user(self):
        return self._current_user

    def auth_ok(self):
        return self._current_user is not None and self._auth_error is None

    @property
    def auth_error(self):
        return self._auth_error

    def get_repository(self, workspace, name):
        url = f"{self.BASE_API_URL}repositories/{workspace}/{name}"
        return self._request_json(url)

    # Legacy aliases kept for compatibility with previous script names.
    def get_repo_list(self, workspace=None, paginated=False):
        _ = paginated  # Legacy argument preserved for backward compatibility.
        return self.list_repositories(workspace=workspace)

    def get_repositories_by_permission(self, role="member"):
        return self.list_repositories(role=role)

    def get_branches(self, name):
        return self.list_branches(name)


class GitHubSource(RemoteProvider):
    provider_name = "github"
    BASE_API_URL = "https://api.github.com/"

    def __init__(self, username, token, timeout=20, retries=3):
        self._username = username
        self._token = token
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
            }
        )

        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"GET"},
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)

        self._current_user = None
        self._auth_error = None
        try:
            self._current_user = self.get_user_info()
        except (AuthenticationError, RemoteAPIError) as exc:
            self._auth_error = str(exc)

    def _request(self, url, params=None):
        try:
            response = self._session.get(url, params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            raise RemoteAPIError(f"Request to '{url}' failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed for '{url}' "
                f"(status {response.status_code})"
            )
        if response.status_code >= 400:
            raise RemoteAPIError(f"Request to '{url}' failed with status {response.status_code}")
        return response

    def _request_json(self, url, params=None):
        response = self._request(url, params=params)
        try:
            return response.json()
        except ValueError as exc:
            raise RemoteAPIError(f"Invalid JSON received from '{url}'") from exc

    def _get_paginated_results(self, url, params=None):
        values = []
        next_url = url
        next_params = params

        while next_url:
            response = self._request(next_url, params=next_params)
            try:
                page_values = response.json()
            except ValueError as exc:
                raise RemoteAPIError(f"Invalid JSON received from '{next_url}'") from exc

            if not isinstance(page_values, list):
                raise RemoteAPIError(
                    f"Paginated endpoint '{next_url}' returned a non-list payload"
                )

            values.extend(page_values)
            next_url = response.links.get("next", {}).get("url")
            next_params = None

        return values

    def _normalize_repository_payload(self, repository):
        clone_links = []
        ssh_url = repository.get("ssh_url")
        if ssh_url:
            clone_links.append({"name": "ssh", "href": ssh_url})
        https_url = repository.get("clone_url")
        if https_url:
            clone_links.append({"name": "https", "href": https_url})

        links = repository.setdefault("links", {})
        links["clone"] = clone_links
        return repository

    def get_user_info(self):
        return self._request_json(self.BASE_API_URL + "user")

    def list_repositories(self, workspace=None, role="member"):
        _ = role
        if workspace:
            url = f"{self.BASE_API_URL}orgs/{workspace}/repos"
            return self._get_paginated_results(url, params={"per_page": 100, "type": "all"})

        url = self.BASE_API_URL + "user/repos"
        return self._get_paginated_results(
            url,
            params={
                "per_page": 100,
                "affiliation": "owner,collaborator,organization_member",
                "visibility": "all",
            },
        )

    def get_repository(self, workspace, name):
        url = f"{self.BASE_API_URL}repos/{workspace}/{name}"
        repository = self._request_json(url)
        return self._normalize_repository_payload(repository)

    def list_branches(self, full_name):
        url = f"{self.BASE_API_URL}repos/{full_name}/branches"
        return self._get_paginated_results(url, params={"per_page": 100})

    @property
    def current_user(self):
        return self._current_user

    def auth_ok(self):
        return self._current_user is not None and self._auth_error is None

    @property
    def auth_error(self):
        return self._auth_error


class _NotImplementedProvider(RemoteProvider):
    provider_name = "not-implemented"

    def __init__(self, provider_name):
        self._provider_name = provider_name
        self._auth_error = f"Provider '{provider_name}' is not implemented yet."

    def _raise_not_implemented(self):
        raise ProviderNotImplementedError(self._auth_error)

    def get_user_info(self):
        self._raise_not_implemented()

    def list_repositories(self, workspace=None, role="member"):
        self._raise_not_implemented()

    def get_repository(self, workspace, name):
        self._raise_not_implemented()

    def list_branches(self, full_name):
        self._raise_not_implemented()

    def auth_ok(self):
        return False

    @property
    def auth_error(self):
        return self._auth_error


class GitLabSource(RemoteProvider):
    provider_name = "gitlab"

    BASE_API_URL = "https://gitlab.com/api/v4/"

    def __init__(self, username, token, timeout=20, retries=3):
        self._username = username
        self._token = token
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "PRIVATE-TOKEN": self._token,
                "Accept": "application/json",
            }
        )

        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"GET"},
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)

        self._current_user = None
        self._auth_error = None
        try:
            self._current_user = self.get_user_info()
        except (AuthenticationError, RemoteAPIError) as exc:
            self._auth_error = str(exc)

    def _request(self, url, params=None):
        try:
            response = self._session.get(url, params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            raise RemoteAPIError(f"Request to '{url}' failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed for '{url}' "
                f"(status {response.status_code})"
            )
        if response.status_code >= 400:
            raise RemoteAPIError(f"Request to '{url}' failed with status {response.status_code}")
        return response

    def _request_json(self, url, params=None):
        response = self._request(url, params=params)
        try:
            return response.json()
        except ValueError as exc:
            raise RemoteAPIError(f"Invalid JSON received from '{url}'") from exc

    def _get_paginated_results(self, url, params=None):
        values = []
        page = 1
        base_params = dict(params or {})

        while True:
            page_params = dict(base_params)
            page_params["per_page"] = 100
            page_params["page"] = page
            response = self._request(url, params=page_params)
            try:
                page_values = response.json()
            except ValueError as exc:
                raise RemoteAPIError(f"Invalid JSON received from '{url}'") from exc
            if not isinstance(page_values, list):
                raise RemoteAPIError(
                    f"Paginated endpoint '{url}' returned a non-list payload"
                )

            values.extend(page_values)
            next_page = response.headers.get("X-Next-Page")
            if not next_page:
                break
            try:
                page = int(next_page)
            except ValueError as exc:
                raise RemoteAPIError(
                    f"Invalid pagination header from '{url}': X-Next-Page={next_page!r}"
                ) from exc

        return values

    def _normalize_repository_payload(self, repository):
        if "full_name" not in repository:
            path_with_namespace = repository.get("path_with_namespace")
            if path_with_namespace:
                repository["full_name"] = path_with_namespace

        clone_links = []
        ssh_url = repository.get("ssh_url_to_repo")
        if ssh_url:
            clone_links.append({"name": "ssh", "href": ssh_url})
        https_url = repository.get("http_url_to_repo")
        if https_url:
            clone_links.append({"name": "https", "href": https_url})

        links = repository.setdefault("links", {})
        links["clone"] = clone_links
        return repository

    def get_user_info(self):
        return self._request_json(self.BASE_API_URL + "user")

    def list_repositories(self, workspace=None, role="member"):
        _ = role
        if workspace:
            encoded_workspace = quote(workspace, safe="")
            url = f"{self.BASE_API_URL}groups/{encoded_workspace}/projects"
            repositories = self._get_paginated_results(
                url,
                params={"include_subgroups": "true"},
            )
        else:
            url = self.BASE_API_URL + "projects"
            repositories = self._get_paginated_results(
                url,
                params={"membership": "true", "order_by": "id", "sort": "asc"},
            )

        return [self._normalize_repository_payload(repo) for repo in repositories]

    def get_repository(self, workspace, name):
        full_name = quote(f"{workspace}/{name}", safe="")
        url = f"{self.BASE_API_URL}projects/{full_name}"
        repository = self._request_json(url)
        return self._normalize_repository_payload(repository)

    def list_branches(self, full_name):
        encoded_full_name = quote(full_name, safe="")
        url = f"{self.BASE_API_URL}projects/{encoded_full_name}/repository/branches"
        return self._get_paginated_results(url)

    @property
    def current_user(self):
        return self._current_user

    def auth_ok(self):
        return self._current_user is not None and self._auth_error is None

    @property
    def auth_error(self):
        return self._auth_error
