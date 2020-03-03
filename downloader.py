import argparse
import getpass

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

print(manager.get_repo_list(workspace))
