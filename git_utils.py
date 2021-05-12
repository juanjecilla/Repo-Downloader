import json

import requests
from git import Repo
from requests.auth import HTTPBasicAuth


def get_repos(username, password, team):
    bitbucket_api_root = 'https://api.bitbucket.org/2.0/repositories/'
    raw_request = requests.get(bitbucket_api_root + team, auth=HTTPBasicAuth(username, password))
    dict_request = json.loads(raw_request.content.decode('utf-8'))
    repos = dict_request['values']
    return repos

def get_teams(username, password, team):
    bitbucket_api_root = 'https://api.bitbucket.org/2.0/repositories/'
    raw_request = requests.get(bitbucket_api_root + team, auth=HTTPBasicAuth(username, password))
    dict_request = json.loads(raw_request.content.decode('utf-8'))
    repos = dict_request['values']
    return repos


def get_branches(username, password, url):
    raw_request = requests.get(url, auth=HTTPBasicAuth(username, password))
    dict_request = json.loads(raw_request.content.decode('utf-8'))
    branches = dict_request['values']

    if "next" in dict_request:
        for branch in get_branches(username, password, dict_request["next"]):
            branches.append(branch)

    return branches


def clone_repo(repo_name, local_path="./repo/"):
    cloned_repo = Repo.clone_from(repo_name, local_path, env={'GIT_SSH_COMMAND': 'ssh -i ~/.ssh/id_rsa'})
    return cloned_repo
