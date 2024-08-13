import argparse
import getpass
import os

from utils import url_utils

from data.source.remote_sources import BitbucketSource

my_parser = argparse.ArgumentParser(allow_abbrev=False, description='Download repositories from remote origins')

my_parser.add_argument("-u", "--username", type=str, help='Remote origin username', required=True)
my_parser.add_argument("-w", "--workspace", type=str, help='Used workspace', required=False)

args = my_parser.parse_args()

username = args.username
workspace = args.workspace

password = getpass.getpass("Enter account password: ")

manager = BitbucketSource(username, password)
if not manager.current_user:
    print("Error connecting with remote origin")
    exit(1)

print("Requesting repositories with permission")
repositories = manager.get_repositories_by_permission()
print("{} repositories found!".format(len(repositories)))

for index, repository in enumerate(repositories):
    try:
        repo_workspace = repository["repository"]["full_name"].split("/")[0]
        repo_name = repository["repository"]["full_name"].split("/")[1]
        print("Starting {} repository {}/{}".format(repo_name, index + 1, len(repositories)))

        extended_repo = manager.get_repository(repo_workspace, repo_name)

        if os.path.isdir("repo/{}".format(repo_name)):
            repo = manager.open_repo("repo/{}".format(repo_name))
        else:
            clone_url = url_utils.get_ssh_url_from_list(extended_repo["links"]["clone"])

            print("\tCloning repository")
            repo = manager.clone_repo(clone_url, "./repo/{}".format(repo_name))
            print("\tRepository cloned!")

        branches = manager.get_branches(repository["repository"]["full_name"])

        for branch_index, branch in enumerate(branches):
            branch_name = branch["name"]
            print("\t\tChecking out branch {} {}/{}".format(branch_name, branch_index + 1, len(branches)))
            repo.git.checkout(branch_name)
            print("\t\tBranch checkout finished!")

        print("Finishing {} repository".format(repo_name))
    except Exception as err:
        print(err)
        print("Oops... Something happened... Moving to next repo")

print("All repos finished!")
