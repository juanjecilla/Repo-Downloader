import argparse
import getpass
import importlib
import os
import sys
import time

from utils import url_utils
from utils.errors import (
    AuthenticationError,
    ProviderConfigurationError,
    ProviderNotImplementedError,
    RemoteAPIError,
    RepoDownloaderError,
    RepositorySyncError,
)
from utils.log_utils import NullLogger, RunLogger
from utils.repo_utils import (
    build_backup_paths,
    is_archived_repository,
    normalize_repo_patterns,
    parse_repository_entry,
    repository_matches_filters,
)

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
    parser.add_argument(
        "--log-format",
        choices=("text", "json"),
        default="text",
        help="Log output format.",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Optional path to write logs in the selected format.",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help=(
            "Include repository full-name patterns (glob). "
            "Can be repeated or comma-separated."
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help=(
            "Exclude repository full-name patterns (glob). "
            "Can be repeated or comma-separated."
        ),
    )
    return parser


def emit_text(logger, message):
    if getattr(logger, "log_format", "text") == "text":
        print(message)


def resolve_token(token_env, logger=None):
    logger = logger or NullLogger()
    if token_env:
        token = os.environ.get(token_env)
        if token:
            logger.event(
                "auth.token.source",
                outcome="success",
                token_env=token_env,
                source="environment",
            )
            return token
        fallback_msg = (
            f"Environment variable '{token_env}' was not set. Falling back to prompt."
        )
        logger.event(
            "auth.token.source",
            outcome="fallback",
            level="WARNING",
            token_env=token_env,
            source="prompt",
            message=fallback_msg,
        )
        emit_text(logger, fallback_msg)
    else:
        logger.event("auth.token.source", outcome="prompt", source="prompt")
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
        raise ProviderConfigurationError(
            "Argument '--username' is required for provider 'bitbucket'."
        )

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


def sync_mirror(git_source, clone_url, mirror_path, dry_run, logger, provider_name, repository):
    if dry_run:
        if os.path.isdir(mirror_path):
            emit_text(logger, f"\t[DRY-RUN] Would update mirror: {mirror_path}")
            logger.event(
                "sync.mirror.update",
                outcome="planned",
                provider=provider_name,
                repository=repository,
                mode="mirror",
                path=mirror_path,
            )
        else:
            emit_text(logger, f"\t[DRY-RUN] Would create mirror clone: {mirror_path}")
            logger.event(
                "sync.mirror.clone",
                outcome="planned",
                provider=provider_name,
                repository=repository,
                mode="mirror",
                path=mirror_path,
            )
        return

    started_at = time.monotonic()
    if os.path.isdir(mirror_path):
        git_source.update_mirror(mirror_path)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        emit_text(logger, "\tMirror updated.")
        logger.event(
            "sync.mirror.update",
            outcome="success",
            provider=provider_name,
            repository=repository,
            mode="mirror",
            path=mirror_path,
            duration_ms=duration_ms,
        )
    else:
        git_source.clone_repo(clone_url, mirror_path, mirror=True)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        emit_text(logger, "\tMirror cloned.")
        logger.event(
            "sync.mirror.clone",
            outcome="success",
            provider=provider_name,
            repository=repository,
            mode="mirror",
            path=mirror_path,
            duration_ms=duration_ms,
        )


def sync_working(
    git_source,
    provider,
    full_name,
    clone_url,
    working_path,
    dry_run,
    logger,
    provider_name,
):
    if dry_run:
        if os.path.isdir(working_path):
            emit_text(logger, f"\t[DRY-RUN] Would fetch working clone: {working_path}")
            logger.event(
                "sync.working.fetch",
                outcome="planned",
                provider=provider_name,
                repository=full_name,
                mode="working",
                path=working_path,
            )
        else:
            emit_text(logger, f"\t[DRY-RUN] Would clone working copy: {working_path}")
            logger.event(
                "sync.working.clone",
                outcome="planned",
                provider=provider_name,
                repository=full_name,
                mode="working",
                path=working_path,
            )
        return

    started_at = time.monotonic()
    if os.path.isdir(working_path):
        repo = git_source.fetch_working_copy(working_path)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        emit_text(logger, "\tWorking copy fetched.")
        logger.event(
            "sync.working.fetch",
            outcome="success",
            provider=provider_name,
            repository=full_name,
            mode="working",
            path=working_path,
            duration_ms=duration_ms,
        )
    else:
        repo = git_source.clone_repo(clone_url, working_path, mirror=False)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        emit_text(logger, "\tWorking copy cloned.")
        logger.event(
            "sync.working.clone",
            outcome="success",
            provider=provider_name,
            repository=full_name,
            mode="working",
            path=working_path,
            duration_ms=duration_ms,
        )

    branches = provider.list_branches(full_name) or []
    logger.event(
        "sync.working.branches.list",
        outcome="success",
        provider=provider_name,
        repository=full_name,
        mode="working",
        branch_count=len(branches),
    )
    if not branches:
        emit_text(logger, "\tNo branches reported by provider.")
        return

    for branch_index, branch in enumerate(branches):
        branch_name = branch.get("name")
        if not branch_name:
            continue
        emit_text(
            logger,
            f"\t\tChecking out branch {branch_name} "
            f"{branch_index + 1}/{len(branches)}",
        )
        branch_started_at = time.monotonic()
        try:
            git_source.checkout_branch(repo, branch_name)
            duration_ms = int((time.monotonic() - branch_started_at) * 1000)
            emit_text(logger, "\t\tBranch checkout finished.")
            logger.event(
                "sync.working.branch.checkout",
                outcome="success",
                provider=provider_name,
                repository=full_name,
                mode="working",
                branch=branch_name,
                duration_ms=duration_ms,
            )
        except RepositorySyncError as exc:
            duration_ms = int((time.monotonic() - branch_started_at) * 1000)
            emit_text(logger, f"\t\t[WARN] {exc}")
            logger.event(
                "sync.working.branch.checkout",
                outcome="failed",
                level="WARNING",
                provider=provider_name,
                repository=full_name,
                mode="working",
                branch=branch_name,
                error=str(exc),
                duration_ms=duration_ms,
            )


def run_backup(args, provider, git_source, logger=None):
    logger = logger or NullLogger()
    emit_text(logger, "Requesting repositories with permission")
    logger.event("repositories.request", outcome="start", provider=args.provider, mode=args.mode)
    repositories = provider.list_repositories(workspace=args.workspace, role=args.role)
    if repositories is None:
        raise RemoteAPIError("Provider returned no repository data.")

    logger.event(
        "repositories.received",
        outcome="success",
        provider=args.provider,
        mode=args.mode,
        repository_count=len(repositories),
    )
    emit_text(logger, f"{len(repositories)} repositories found!")
    stats = {"processed": 0, "succeeded": 0, "skipped": 0, "failed": 0}

    for index, repository_entry in enumerate(repositories):
        stats["processed"] += 1
        repository_for_log = "unknown"
        try:
            parsed = parse_repository_entry(repository_entry)
            repo_workspace = parsed["workspace"]
            repo_name = parsed["name"]
            full_name = parsed["full_name"]
            summary_repo = parsed["repository"]
            repository_for_log = full_name

            matched_filters, filter_reason, filter_detail = repository_matches_filters(
                full_name=full_name,
                include_patterns=args.include,
                exclude_patterns=args.exclude,
            )
            if not matched_filters:
                dry_run_prefix = "[DRY-RUN] " if args.dry_run else ""
                emit_text(
                    logger,
                    f"\t{dry_run_prefix}Skipping repository by filter: {filter_detail}.",
                )
                logger.event(
                    "repository.skip",
                    outcome="skipped",
                    provider=args.provider,
                    repository=full_name,
                    mode=args.mode,
                    reason=filter_reason,
                    detail=filter_detail,
                )
                stats["skipped"] += 1
                continue

            logger.event(
                "repository.start",
                outcome="start",
                provider=args.provider,
                repository=full_name,
                mode=args.mode,
                index=index + 1,
                total=len(repositories),
            )
            emit_text(logger, f"Starting {repo_name} repository {index + 1}/{len(repositories)}")
            extended_repo = provider.get_repository(repo_workspace, repo_name)
            if extended_repo is None:
                error_msg = (
                    f"Provider did not return details for repository '{full_name}'"
                )
                raise RemoteAPIError(error_msg)

            if not args.include_archived and is_archived_repository(summary_repo, extended_repo):
                emit_text(logger, "\tSkipping archived repository.")
                logger.event(
                    "repository.skip",
                    outcome="skipped",
                    provider=args.provider,
                    repository=full_name,
                    mode=args.mode,
                    reason="archived",
                )
                stats["skipped"] += 1
                continue

            clone_links = extended_repo.get("links", {}).get("clone", [])
            clone_url = url_utils.get_ssh_url_from_list(clone_links)
            if not clone_url:
                emit_text(logger, "\tSkipping repository without SSH clone URL.")
                logger.event(
                    "repository.skip",
                    outcome="skipped",
                    provider=args.provider,
                    repository=full_name,
                    mode=args.mode,
                    reason="missing_ssh_clone_url",
                )
                stats["skipped"] += 1
                continue

            paths = build_backup_paths(args.output_dir, args.provider, repo_workspace, repo_name)
            if not args.dry_run:
                os.makedirs(paths["base_dir"], exist_ok=True)

            for mode in selected_modes(args.mode):
                if mode == "mirror":
                    sync_mirror(
                        git_source,
                        clone_url,
                        paths["mirror_path"],
                        args.dry_run,
                        logger,
                        args.provider,
                        full_name,
                    )
                elif mode == "working":
                    sync_working(
                        git_source,
                        provider,
                        full_name,
                        clone_url,
                        paths["working_path"],
                        args.dry_run,
                        logger,
                        args.provider,
                    )

            emit_text(logger, f"Finishing {repo_name} repository")
            logger.event(
                "repository.finish",
                outcome="success",
                provider=args.provider,
                repository=full_name,
                mode=args.mode,
            )
            stats["succeeded"] += 1
        except (KeyError, TypeError, ValueError, RemoteAPIError, RepositorySyncError) as exc:
            logger.event(
                "repository.finish",
                outcome="failed",
                level="ERROR",
                provider=args.provider,
                repository=repository_for_log,
                mode=args.mode,
                error=str(exc),
            )
            emit_text(logger, f"[ERROR] Failed processing repository entry: {exc}")
            emit_text(logger, "Moving to next repository.")
            stats["failed"] += 1

    return stats


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.include = normalize_repo_patterns(args.include)
    args.exclude = normalize_repo_patterns(args.exclude)
    logger = RunLogger(log_format=args.log_format, log_file=args.log_file)

    logger.event(
        "run.start",
        outcome="start",
        provider=args.provider,
        mode=args.mode,
        workspace=args.workspace,
        output_dir=os.path.expanduser(args.output_dir),
        dry_run=args.dry_run,
        include_archived=args.include_archived,
        ssh_key_path=args.ssh_key_path,
        token_env=args.token_env,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        log_format=args.log_format,
    )

    try:
        token = resolve_token(args.token_env, logger=logger)
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
        stats = run_backup(args, provider, git_source, logger=logger)
    except RepoDownloaderError as exc:
        logger.event(
            "run.finish",
            outcome="failed",
            level="ERROR",
            provider=args.provider,
            error=str(exc),
        )
        emit_text(logger, f"[ERROR] {exc}")
        logger.close()
        return 1
    except KeyboardInterrupt:
        logger.event("run.finish", outcome="interrupted", level="WARNING", provider=args.provider)
        emit_text(logger, "\nInterrupted by user.")
        logger.close()
        return 130

    exit_code = 0 if stats["failed"] == 0 else 2
    logger.event(
        "run.finish",
        outcome="success" if exit_code == 0 else "partial_failure",
        provider=args.provider,
        mode=args.mode,
        processed=stats["processed"],
        succeeded=stats["succeeded"],
        skipped=stats["skipped"],
        failed=stats["failed"],
    )
    emit_text(
        logger,
        "All repos finished! "
        f"processed={stats['processed']}, succeeded={stats['succeeded']}, "
        f"skipped={stats['skipped']}, failed={stats['failed']}"
    )
    logger.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
