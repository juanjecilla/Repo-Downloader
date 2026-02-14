import argparse
import getpass
import importlib
import os
import sys

from utils import url_utils
from utils.errors import (
    AuthenticationError,
    ProviderConfigurationError,
    ProviderNotImplementedError,
    RemoteAPIError,
    RepoDownloaderError,
    RepositorySyncError,
)
from utils.repo_utils import build_backup_paths, is_archived_repository, parse_repository_entry

PROVIDER_CLASS_PATHS = {
    "bitbucket": ("data.source.remote_sources", "BitbucketSource"),
    "github": ("data.source.remote_sources", "GitHubSource"),
    "gitlab": ("data.source.remote_sources", "GitLabSource"),
}


def build_parser():
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Download and back up repositories from supported remote providers.",
    )

    parser.add_argument("-u", "--username", type=str, help="Remote account username")
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDER_CLASS_PATHS.keys()),
        default="bitbucket",
        help="Repository provider backend.",
    )
    parser.add_argument(
        "--mode",
        choices=("mirror", "working", "both"),
        default="both",
        help="Backup mode to run.",
    )
    parser.add_argument("-w", "--workspace", type=str, help="Workspace filter (optional)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./backups",
        help="Root directory where backups are stored.",
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived repositories in backup.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned actions without cloning/fetching.",
    )
    parser.add_argument(
        "--ssh-key-path",
        type=str,
        default="~/.ssh/id_rsa",
        help="Path to SSH private key used for git operations.",
    )
    parser.add_argument(
        "--role",
        type=str,
        default="member",
        help="Provider role filter (Bitbucket only).",
    )
    parser.add_argument(
        "--token-env",
        type=str,
        default=None,
        help="Environment variable name containing the provider token/app password.",
    )
    return parser


def resolve_token(token_env):
    if token_env:
        token = os.environ.get(token_env)
        if token:
            return token
        print(f"Token environment variable '{token_env}' was not set. Falling back to prompt.")
    return getpass.getpass("Enter account token / app password: ")


def selected_modes(mode):
    if mode == "both":
        return ("mirror", "working")
    return (mode,)


def create_provider(args, token):
    provider_name = args.provider
    if provider_name not in PROVIDER_CLASS_PATHS:
        raise ProviderConfigurationError(f"Unknown provider '{provider_name}'.")

    if provider_name == "bitbucket" and not args.username:
        raise ProviderConfigurationError("Argument '--username' is required for provider 'bitbucket'.")

    module_name, class_name = PROVIDER_CLASS_PATHS[provider_name]
    try:
        provider_module = importlib.import_module(module_name)
        provider_class = getattr(provider_module, class_name)
    except ModuleNotFoundError as exc:
        raise ProviderConfigurationError(
            f"Missing dependency '{exc.name}' for provider '{provider_name}'. "
            "Install project dependencies with `pip install -r requirements.txt`."
        ) from exc

    return provider_class(args.username, token)


def sync_mirror(git_source, clone_url, mirror_path, dry_run):
    if dry_run:
        if os.path.isdir(mirror_path):
            print(f"\t[DRY-RUN] Would update mirror: {mirror_path}")
        else:
            print(f"\t[DRY-RUN] Would create mirror clone: {mirror_path}")
        return

    if os.path.isdir(mirror_path):
        git_source.update_mirror(mirror_path)
        print("\tMirror updated.")
    else:
        git_source.clone_repo(clone_url, mirror_path, mirror=True)
        print("\tMirror cloned.")


def sync_working(git_source, provider, full_name, clone_url, working_path, dry_run):
    if dry_run:
        if os.path.isdir(working_path):
            print(f"\t[DRY-RUN] Would fetch working clone: {working_path}")
        else:
            print(f"\t[DRY-RUN] Would clone working copy: {working_path}")
        return

    if os.path.isdir(working_path):
        repo = git_source.fetch_working_copy(working_path)
        print("\tWorking copy fetched.")
    else:
        repo = git_source.clone_repo(clone_url, working_path, mirror=False)
        print("\tWorking copy cloned.")

    branches = provider.list_branches(full_name)
    if not branches:
        print("\tNo branches reported by provider.")
        return

    for branch_index, branch in enumerate(branches):
        branch_name = branch.get("name")
        if not branch_name:
            continue
        print(f"\t\tChecking out branch {branch_name} {branch_index + 1}/{len(branches)}")
        try:
            git_source.checkout_branch(repo, branch_name)
            print("\t\tBranch checkout finished.")
        except RepositorySyncError as exc:
            print(f"\t\t[WARN] {exc}")


def run_backup(args, provider, git_source):
    print("Requesting repositories with permission")
    repositories = provider.list_repositories(workspace=args.workspace, role=args.role)
    if repositories is None:
        raise RemoteAPIError("Provider returned no repository data.")

    print("{} repositories found!".format(len(repositories)))
    stats = {"processed": 0, "succeeded": 0, "skipped": 0, "failed": 0}

    for index, repository_entry in enumerate(repositories):
        stats["processed"] += 1
        try:
            parsed = parse_repository_entry(repository_entry)
            repo_workspace = parsed["workspace"]
            repo_name = parsed["name"]
            full_name = parsed["full_name"]
            summary_repo = parsed["repository"]

            print(f"Starting {repo_name} repository {index + 1}/{len(repositories)}")
            extended_repo = provider.get_repository(repo_workspace, repo_name)
            if extended_repo is None:
                raise RemoteAPIError(f"Provider did not return details for repository '{full_name}'")

            if not args.include_archived and is_archived_repository(summary_repo, extended_repo):
                print("\tSkipping archived repository.")
                stats["skipped"] += 1
                continue

            clone_links = extended_repo.get("links", {}).get("clone", [])
            clone_url = url_utils.get_ssh_url_from_list(clone_links)
            if not clone_url:
                print("\tSkipping repository without SSH clone URL.")
                stats["skipped"] += 1
                continue

            paths = build_backup_paths(args.output_dir, args.provider, repo_workspace, repo_name)
            if not args.dry_run:
                os.makedirs(paths["base_dir"], exist_ok=True)

            for mode in selected_modes(args.mode):
                if mode == "mirror":
                    sync_mirror(git_source, clone_url, paths["mirror_path"], args.dry_run)
                elif mode == "working":
                    sync_working(git_source, provider, full_name, clone_url, paths["working_path"], args.dry_run)

            print(f"Finishing {repo_name} repository")
            stats["succeeded"] += 1
        except (KeyError, TypeError, ValueError, RemoteAPIError, RepositorySyncError) as exc:
            print(f"[ERROR] Failed processing repository entry: {exc}")
            print("Moving to next repository.")
            stats["failed"] += 1

    return stats


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        token = resolve_token(args.token_env)
        provider = create_provider(args, token)
        if not provider.auth_ok():
            message = provider.auth_error or "Unknown authentication error."
            if "not implemented" in message.lower():
                raise ProviderNotImplementedError(message)
            raise AuthenticationError(message)

        try:
            git_module = importlib.import_module("data.source.git_source")
            git_source_class = getattr(git_module, "GitSource")
        except ModuleNotFoundError as exc:
            raise ProviderConfigurationError(
                f"Missing dependency '{exc.name}' required for git operations. "
                "Install project dependencies with `pip install -r requirements.txt`."
            ) from exc

        git_source = git_source_class(key_path=args.ssh_key_path)
        stats = run_backup(args, provider, git_source)
    except RepoDownloaderError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130

    print(
        "All repos finished! "
        f"processed={stats['processed']}, succeeded={stats['succeeded']}, "
        f"skipped={stats['skipped']}, failed={stats['failed']}"
    )
    return 0 if stats["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
