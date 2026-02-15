# pylint: disable=too-many-lines

import argparse
import fnmatch
import getpass
import importlib
import os
import shutil
import sys
import time

from utils import url_utils
from utils.errors import (
    AuthenticationError,
    ProviderConfigurationError,
    ProviderNotImplementedError,
    RemoteAPIError,
    RepoDownloaderError,
    RunLockError,
    RepositorySyncError,
)
from utils.log_utils import NullLogger, RunLogger
from utils.repo_utils import (
    acquire_run_lock,
    build_backup_paths,
    build_checkpoint_path,
    build_snapshot_path,
    collect_snapshot_paths,
    create_snapshot_archive,
    delete_artifact_path,
    is_archived_repository,
    load_checkpoint,
    normalize_repo_patterns,
    parse_repository_entry,
    plan_retention_deletions,
    remove_checkpoint,
    release_run_lock,
    repository_matches_filters,
    save_checkpoint,
)

PROVIDER_CLASS_PATHS = {
    "bitbucket": ("data.source.remote_sources", "BitbucketSource"),
    "github": ("data.source.remote_sources", "GitHubSource"),
    "gitlab": ("data.source.remote_sources", "GitLabSource"),
}
FAILURE_TYPE_ORDER = ("api", "auth", "clone", "fetch", "checkout", "other")


def build_parser():
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Download and back up repositories from supported remote providers.",
    )

    parser.add_argument("-u", "--username", type=str, help="Remote account username")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("backup", "list-backups", "validate-restore"),
        default="backup",
        help="CLI command to execute.",
    )
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
        "--snapshot-format",
        choices=("zip", "tar.gz"),
        default=None,
        help="Optional snapshot archive format to export mirror backups.",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=str,
        default="./snapshots",
        help="Root directory where snapshot archives are stored.",
    )
    parser.add_argument(
        "--retain-days",
        type=int,
        default=None,
        help="Delete snapshot/working artifacts older than this many days.",
    )
    parser.add_argument(
        "--retain-count",
        type=int,
        default=None,
        help="Keep only the most recent N snapshot/working artifacts per repository.",
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
    parser.add_argument(
        "--branch",
        action="append",
        default=None,
        help=(
            "Limit working-mode checkout to specific branch names. "
            "Can be repeated or comma-separated."
        ),
    )
    parser.add_argument(
        "--branch-pattern",
        action="append",
        default=None,
        help=(
            "Limit working-mode checkout using glob branch patterns. "
            "Can be repeated or comma-separated."
        ),
    )
    parser.add_argument(
        "--default-branch-only",
        action="store_true",
        help="In working mode, only checkout the repository default branch.",
    )
    parser.add_argument(
        "--repo-retries",
        type=int,
        default=0,
        help="Additional retries per repository after a failure.",
    )
    parser.add_argument(
        "--force-lock",
        action="store_true",
        help="Replace an existing active run lock for the selected provider/output root.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume backup using checkpoint state from a previous interrupted run.",
    )
    parser.add_argument(
        "--backup-path",
        type=str,
        default=None,
        help="Backup path to validate with the 'validate-restore' command.",
    )
    parser.add_argument(
        "--restore-dir",
        type=str,
        default="./restore-validation",
        help="Directory where 'validate-restore' clones the backup for validation.",
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


def normalize_cli_list(raw_values):
    """Normalize repeatable/comma-separated CLI list values."""
    normalized = []
    if not raw_values:
        return normalized

    for raw_value in raw_values:
        for part in raw_value.split(","):
            cleaned = part.strip()
            if cleaned:
                normalized.append(cleaned)
    return normalized


def classify_repository_failure(exc):
    failure_type = "other"
    if isinstance(exc, AuthenticationError):
        failure_type = "auth"
    elif isinstance(exc, RemoteAPIError):
        failure_type = "api"
    elif isinstance(exc, RepositorySyncError):
        message = str(exc).lower()
        if "checkout" in message:
            failure_type = "checkout"
        elif "fetch" in message:
            failure_type = "fetch"
        elif "clon" in message:
            failure_type = "clone"
    elif isinstance(exc, (KeyError, TypeError, ValueError)):
        failure_type = "api"
    return failure_type


def make_failure_counters():
    return {failure_type: 0 for failure_type in FAILURE_TYPE_ORDER}


def format_failure_counters(counters):
    non_zero = [
        f"{failure_type}={counters[failure_type]}"
        for failure_type in FAILURE_TYPE_ORDER
        if counters.get(failure_type, 0) > 0
    ]
    if non_zero:
        return ", ".join(non_zero)
    return "none"


def get_default_branch_name(extended_repository):
    """Extract provider default branch name when available."""
    if not isinstance(extended_repository, dict):
        return None

    main_branch = extended_repository.get("mainbranch")
    if isinstance(main_branch, dict):
        branch_name = main_branch.get("name")
        if branch_name:
            return branch_name

    default_branch = extended_repository.get("default_branch")
    if isinstance(default_branch, dict):
        branch_name = default_branch.get("name")
        if branch_name:
            return branch_name
    if isinstance(default_branch, str):
        return default_branch

    return None


def select_working_branches(
    branches,
    explicit_branch_names,
    branch_patterns,
    default_branch_only=False,
    default_branch_name=None,
):
    """Select branches for working checkout based on CLI selectors."""
    if not branches:
        return []

    if default_branch_only:
        if not default_branch_name:
            return []
        return [branch for branch in branches if branch.get("name") == default_branch_name]

    has_explicit_filters = bool(explicit_branch_names or branch_patterns)
    if not has_explicit_filters:
        return branches

    explicit_names = set(explicit_branch_names or [])
    patterns = branch_patterns or []

    selected = []
    for branch in branches:
        branch_name = branch.get("name")
        if not branch_name:
            continue
        if branch_name in explicit_names:
            selected.append(branch)
            continue
        if any(fnmatch.fnmatchcase(branch_name, pattern) for pattern in patterns):
            selected.append(branch)

    return selected


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


def snapshot_mirror_if_enabled(
    mirror_path,
    dry_run,
    logger,
    provider_name,
    workspace,
    repository_name,
    full_name,
    snapshot_format=None,
    snapshot_dir="./snapshots",
):
    if not snapshot_format:
        return None

    snapshot_path = build_snapshot_path(
        snapshot_dir=snapshot_dir,
        provider=provider_name,
        workspace=workspace,
        repository_name=repository_name,
        snapshot_format=snapshot_format,
    )
    if dry_run:
        emit_text(logger, f"\t[DRY-RUN] Would create snapshot: {snapshot_path}")
        logger.event(
            "snapshot.create",
            outcome="planned",
            provider=provider_name,
            repository=full_name,
            mode="mirror",
            format=snapshot_format,
            source_path=mirror_path,
            path=snapshot_path,
        )
        return snapshot_path

    started_at = time.monotonic()
    try:
        created_path = create_snapshot_archive(mirror_path, snapshot_path, snapshot_format)
    except (OSError, ValueError) as exc:
        raise RepositorySyncError(
            f"Failed creating snapshot for repository '{full_name}': {exc}"
        ) from exc

    duration_ms = int((time.monotonic() - started_at) * 1000)
    emit_text(logger, f"\tSnapshot created: {created_path}")
    logger.event(
        "snapshot.create",
        outcome="success",
        provider=provider_name,
        repository=full_name,
        mode="mirror",
        format=snapshot_format,
        source_path=mirror_path,
        path=created_path,
        duration_ms=duration_ms,
    )
    return created_path


def apply_retention_if_enabled(
    logger,
    provider_name,
    workspace,
    repository_name,
    full_name,
    working_path,
    snapshot_dir,
    retain_days=None,
    retain_count=None,
    dry_run=False,
):
    if retain_days is None and retain_count is None:
        return

    snapshot_paths = collect_snapshot_paths(
        snapshot_dir=snapshot_dir,
        provider=provider_name,
        workspace=workspace,
        repository_name=repository_name,
    )
    working_paths = [working_path] if os.path.exists(working_path) else []

    for artifact_type, candidate_paths in (
        ("snapshot", snapshot_paths),
        ("working", working_paths),
    ):
        deletion_paths = plan_retention_deletions(
            candidate_paths,
            retain_days=retain_days,
            retain_count=retain_count,
        )
        for artifact_path in deletion_paths:
            if dry_run:
                emit_text(logger, f"\t[DRY-RUN] Would delete {artifact_type}: {artifact_path}")
                logger.event(
                    "retention.delete",
                    outcome="planned",
                    provider=provider_name,
                    repository=full_name,
                    artifact_type=artifact_type,
                    path=artifact_path,
                    retain_days=retain_days,
                    retain_count=retain_count,
                )
                continue

            try:
                delete_artifact_path(artifact_path)
            except OSError as exc:
                raise RepositorySyncError(
                    f"Failed deleting retained {artifact_type} artifact '{artifact_path}': {exc}"
                ) from exc

            emit_text(logger, f"\tDeleted {artifact_type} artifact: {artifact_path}")
            logger.event(
                "retention.delete",
                outcome="success",
                provider=provider_name,
                repository=full_name,
                artifact_type=artifact_type,
                path=artifact_path,
                retain_days=retain_days,
                retain_count=retain_count,
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
    selected_branch_names,
    selected_branch_patterns,
    default_branch_only=False,
    default_branch_name=None,
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
    selected_branches = select_working_branches(
        branches=branches,
        explicit_branch_names=selected_branch_names,
        branch_patterns=selected_branch_patterns,
        default_branch_only=default_branch_only,
        default_branch_name=default_branch_name,
    )
    logger.event(
        "sync.working.branches.list",
        outcome="success",
        provider=provider_name,
        repository=full_name,
        mode="working",
        branch_count=len(branches),
        selected_branch_count=len(selected_branches),
        default_branch_only=default_branch_only,
        default_branch_name=default_branch_name,
    )
    if not branches:
        emit_text(logger, "\tNo branches reported by provider.")
        return

    if not selected_branches:
        emit_text(logger, "\tSkipping branch checkout: no branches matched selectors.")
        logger.event(
            "sync.working.branches.skip",
            outcome="skipped",
            provider=provider_name,
            repository=full_name,
            mode="working",
            reason="no_selected_branches",
            default_branch_only=default_branch_only,
            default_branch_name=default_branch_name,
        )
        return

    checkout_failures = []
    for branch_index, branch in enumerate(selected_branches):
        branch_name = branch.get("name")
        if not branch_name:
            continue
        emit_text(
            logger,
            f"\t\tChecking out branch {branch_name} "
            f"{branch_index + 1}/{len(selected_branches)}",
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
            checkout_failures.append(branch_name)
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

    if checkout_failures:
        raise RepositorySyncError(
            "One or more branch checkout operations failed: "
            + ", ".join(checkout_failures)
        )


def sync_repository(
    args,
    provider,
    git_source,
    repository_entry,
    index,
    total_repositories,
    logger,
):
    parsed = parse_repository_entry(repository_entry)
    repo_workspace = parsed["workspace"]
    repo_name = parsed["name"]
    full_name = parsed["full_name"]
    summary_repo = parsed["repository"]

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
        return "skipped", full_name

    logger.event(
        "repository.start",
        outcome="start",
        provider=args.provider,
        repository=full_name,
        mode=args.mode,
        index=index + 1,
        total=total_repositories,
    )
    emit_text(logger, f"Starting {repo_name} repository {index + 1}/{total_repositories}")
    extended_repo = provider.get_repository(repo_workspace, repo_name)
    if extended_repo is None:
        error_msg = f"Provider did not return details for repository '{full_name}'"
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
        return "skipped", full_name

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
        return "skipped", full_name

    paths = build_backup_paths(args.output_dir, args.provider, repo_workspace, repo_name)
    if not args.dry_run:
        os.makedirs(paths["base_dir"], exist_ok=True)
    default_branch_name = get_default_branch_name(extended_repo)
    snapshot_format = getattr(args, "snapshot_format", None)
    snapshot_dir = getattr(args, "snapshot_dir", "./snapshots")
    retain_days = getattr(args, "retain_days", None)
    retain_count = getattr(args, "retain_count", None)

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
            snapshot_mirror_if_enabled(
                mirror_path=paths["mirror_path"],
                dry_run=args.dry_run,
                logger=logger,
                provider_name=args.provider,
                workspace=repo_workspace,
                repository_name=repo_name,
                full_name=full_name,
                snapshot_format=snapshot_format,
                snapshot_dir=snapshot_dir,
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
                args.branch_names,
                args.branch_patterns,
                args.default_branch_only,
                default_branch_name,
            )

    apply_retention_if_enabled(
        logger=logger,
        provider_name=args.provider,
        workspace=repo_workspace,
        repository_name=repo_name,
        full_name=full_name,
        working_path=paths["working_path"],
        snapshot_dir=snapshot_dir,
        retain_days=retain_days,
        retain_count=retain_count,
        dry_run=args.dry_run,
    )

    emit_text(logger, f"Finishing {repo_name} repository")
    logger.event(
        "repository.finish",
        outcome="success",
        provider=args.provider,
        repository=full_name,
        mode=args.mode,
    )
    return "success", full_name


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
    stats = {
        "processed": 0,
        "succeeded": 0,
        "skipped": 0,
        "failed": 0,
        "failure_types": make_failure_counters(),
    }
    resume_enabled = bool(getattr(args, "resume", False)) and not args.dry_run
    checkpoint_path = None
    checkpoint_payload = None
    completed_repositories = set()
    if resume_enabled:
        checkpoint_signature = {
            "provider": args.provider,
            "mode": args.mode,
            "workspace": args.workspace,
            "include": args.include,
            "exclude": args.exclude,
        }
        checkpoint_path = build_checkpoint_path(args.output_dir, args.provider)
        checkpoint_payload = load_checkpoint(checkpoint_path)
        if checkpoint_payload.get("signature") == checkpoint_signature:
            completed_repositories = set(checkpoint_payload.get("completed", []))
            logger.event(
                "checkpoint.load",
                outcome="success",
                provider=args.provider,
                mode=args.mode,
                checkpoint_path=checkpoint_path,
                completed_count=len(completed_repositories),
            )
        else:
            completed_repositories = set()
            checkpoint_payload = {
                "signature": checkpoint_signature,
                "completed": [],
            }
            try:
                save_checkpoint(checkpoint_path, checkpoint_payload)
            except OSError as exc:
                raise RemoteAPIError(
                    f"Failed writing checkpoint state to '{checkpoint_path}': {exc}"
                ) from exc
            logger.event(
                "checkpoint.reset",
                outcome="success",
                provider=args.provider,
                mode=args.mode,
                checkpoint_path=checkpoint_path,
                reason="signature_mismatch_or_missing",
            )

    for index, repository_entry in enumerate(repositories):
        stats["processed"] += 1
        if resume_enabled:
            try:
                parsed_for_checkpoint = parse_repository_entry(repository_entry)
                checkpoint_repository = parsed_for_checkpoint["full_name"]
            except (KeyError, TypeError, ValueError):
                checkpoint_repository = None
            if checkpoint_repository and checkpoint_repository in completed_repositories:
                emit_text(
                    logger,
                    f"\tSkipping repository from checkpoint: {checkpoint_repository}.",
                )
                logger.event(
                    "repository.skip",
                    outcome="skipped",
                    provider=args.provider,
                    repository=checkpoint_repository,
                    mode=args.mode,
                    reason="checkpoint_completed",
                )
                stats["skipped"] += 1
                continue

        repository_for_log = "unknown"
        max_attempts = max(1, args.repo_retries + 1)
        for attempt in range(1, max_attempts + 1):
            try:
                outcome, repository_for_log = sync_repository(
                    args,
                    provider,
                    git_source,
                    repository_entry,
                    index,
                    len(repositories),
                    logger,
                )
                if outcome == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["succeeded"] += 1
                    if resume_enabled and repository_for_log:
                        completed_repositories.add(repository_for_log)
                        checkpoint_payload["completed"] = sorted(completed_repositories)
                        try:
                            save_checkpoint(checkpoint_path, checkpoint_payload)
                        except OSError as exc:
                            raise RemoteAPIError(
                                f"Failed writing checkpoint state to '{checkpoint_path}': {exc}"
                            ) from exc
                break
            except (
                KeyError,
                TypeError,
                ValueError,
                AuthenticationError,
                RemoteAPIError,
                RepositorySyncError,
            ) as exc:
                failure_type = classify_repository_failure(exc)
                if attempt < max_attempts:
                    logger.event(
                        "repository.retry",
                        outcome="retrying",
                        level="WARNING",
                        provider=args.provider,
                        repository=repository_for_log,
                        mode=args.mode,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        failure_type=failure_type,
                        error=str(exc),
                    )
                    emit_text(
                        logger,
                        f"[WARN] Repository failed ({failure_type}), retrying "
                        f"{attempt}/{max_attempts - 1}: {exc}",
                    )
                    continue

                logger.event(
                    "repository.finish",
                    outcome="failed",
                    level="ERROR",
                    provider=args.provider,
                    repository=repository_for_log,
                    mode=args.mode,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    failure_type=failure_type,
                    error=str(exc),
                )
                emit_text(logger, f"[ERROR] Failed processing repository entry: {exc}")
                emit_text(logger, "Moving to next repository.")
                stats["failed"] += 1
                stats["failure_types"][failure_type] += 1
                break

    if resume_enabled and stats["failed"] == 0:
        try:
            remove_checkpoint(checkpoint_path)
        except OSError as exc:
            raise RemoteAPIError(
                f"Failed removing checkpoint state '{checkpoint_path}': {exc}"
            ) from exc
        logger.event(
            "checkpoint.clear",
            outcome="success",
            provider=args.provider,
            mode=args.mode,
            checkpoint_path=checkpoint_path,
        )

    return stats


def list_backup_entries(output_dir):
    output_root = os.path.expanduser(output_dir)
    if not os.path.isdir(output_root):
        return []

    entries = []
    for provider in sorted(os.listdir(output_root)):
        provider_path = os.path.join(output_root, provider)
        if not os.path.isdir(provider_path):
            continue
        for workspace in sorted(os.listdir(provider_path)):
            workspace_path = os.path.join(provider_path, workspace)
            if not os.path.isdir(workspace_path):
                continue
            for repository_entry in sorted(os.listdir(workspace_path)):
                artifact_path = os.path.join(workspace_path, repository_entry)
                if repository_entry.endswith(".git") and os.path.isdir(artifact_path):
                    entries.append(
                        {
                            "provider": provider,
                            "workspace": workspace,
                            "repository": repository_entry[: -len(".git")],
                            "mode": "mirror",
                            "path": artifact_path,
                        }
                    )
                    continue
                if os.path.isdir(artifact_path):
                    entries.append(
                        {
                            "provider": provider,
                            "workspace": workspace,
                            "repository": repository_entry,
                            "mode": "working",
                            "path": artifact_path,
                        }
                    )
    return entries


def run_list_backups_command(args):
    entries = list_backup_entries(args.output_dir)
    if not entries:
        print("No backups found.")
        return 0

    print(f"Found {len(entries)} backup entries:")
    for entry in entries:
        print(
            f"{entry['provider']}/{entry['workspace']}/{entry['repository']} "
            f"[{entry['mode']}] -> {entry['path']}"
        )
    return 0


def perform_restore_validation(backup_path, restore_dir):
    backup_root = os.path.expanduser(backup_path)
    target_dir = os.path.expanduser(restore_dir)

    if not os.path.exists(backup_root):
        raise ProviderConfigurationError(f"Backup path does not exist: {backup_root}")

    try:
        git_module = importlib.import_module("git")
        repo_class = getattr(git_module, "Repo")
        git_exc_module = importlib.import_module("git.exc")
        git_error_class = getattr(git_exc_module, "GitError")
    except ModuleNotFoundError as exc:
        raise ProviderConfigurationError(
            f"Missing dependency '{exc.name}' required for restore validation. "
            "Install project dependencies with `pip install -r requirements.txt`."
        ) from exc

    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)
    elif os.path.exists(target_dir):
        os.remove(target_dir)

    try:
        restored_repo = repo_class.clone_from(backup_root, target_dir)
    except git_error_class as exc:
        raise RepositorySyncError(
            f"Failed cloning backup '{backup_root}' into '{target_dir}': {exc}"
        ) from exc
    except (OSError, ValueError, TypeError) as exc:
        raise RepositorySyncError(
            f"Failed cloning backup '{backup_root}' into '{target_dir}': {exc}"
        ) from exc

    branch_names = [head.name for head in getattr(restored_repo, "heads", [])]
    remote_ref_names = []
    try:
        remote_ref_names = [ref.name for ref in restored_repo.remotes.origin.refs]
    except (AttributeError, TypeError, ValueError):
        remote_ref_names = []

    if not branch_names and not remote_ref_names:
        raise RepositorySyncError(
            f"Restore validation failed for '{backup_root}': cloned repository has no refs."
        )

    return {
        "backup_path": backup_root,
        "restore_dir": target_dir,
        "branch_count": len(branch_names),
        "remote_ref_count": len(remote_ref_names),
    }


def run_validate_restore_command(args):
    if not args.backup_path:
        print("[ERROR] --backup-path is required for validate-restore.")
        return 1

    try:
        result = perform_restore_validation(args.backup_path, args.restore_dir)
    except RepoDownloaderError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(
        "Restore validation succeeded: "
        f"backup={result['backup_path']}, restore_dir={result['restore_dir']}, "
        f"branch_count={result['branch_count']}, remote_ref_count={result['remote_ref_count']}"
    )
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list-backups":
        return run_list_backups_command(args)
    if args.command == "validate-restore":
        return run_validate_restore_command(args)

    if args.repo_retries < 0:
        parser.error("--repo-retries must be zero or a positive integer.")
    if args.retain_days is not None and args.retain_days < 0:
        parser.error("--retain-days must be zero or a positive integer.")
    if args.retain_count is not None and args.retain_count < 0:
        parser.error("--retain-count must be zero or a positive integer.")
    args.include = normalize_repo_patterns(args.include)
    args.exclude = normalize_repo_patterns(args.exclude)
    args.branch_names = normalize_cli_list(args.branch)
    args.branch_patterns = normalize_cli_list(args.branch_pattern)
    logger = RunLogger(log_format=args.log_format, log_file=args.log_file)

    logger.event(
        "run.start",
        outcome="start",
        command=args.command,
        provider=args.provider,
        mode=args.mode,
        workspace=args.workspace,
        output_dir=os.path.expanduser(args.output_dir),
        snapshot_format=args.snapshot_format,
        snapshot_dir=os.path.expanduser(args.snapshot_dir),
        dry_run=args.dry_run,
        include_archived=args.include_archived,
        ssh_key_path=args.ssh_key_path,
        token_env=args.token_env,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        branch_names=args.branch_names,
        branch_patterns=args.branch_patterns,
        default_branch_only=args.default_branch_only,
        repo_retries=args.repo_retries,
        retain_days=args.retain_days,
        retain_count=args.retain_count,
        force_lock=args.force_lock,
        resume=args.resume,
        log_format=args.log_format,
    )

    lock_info = None
    exit_code = 1
    try:
        lock_info = acquire_run_lock(
            output_dir=args.output_dir,
            provider=args.provider,
            run_id=logger.run_id,
            force_lock=args.force_lock,
        )
        logger.event(
            "run.lock.acquire",
            outcome="success",
            provider=args.provider,
            lock_path=lock_info["path"],
            force_lock=args.force_lock,
            replaced_stale=lock_info["replaced_stale"],
            replaced_forced=lock_info["replaced_forced"],
        )
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
            failure_types=stats["failure_types"],
        )
        emit_text(
            logger,
            "All repos finished! "
            f"processed={stats['processed']}, succeeded={stats['succeeded']}, "
            f"skipped={stats['skipped']}, failed={stats['failed']}, "
            f"failure_types={format_failure_counters(stats['failure_types'])}"
        )
    except RepoDownloaderError as exc:
        logger.event(
            "run.finish",
            outcome="failed",
            level="ERROR",
            provider=args.provider,
            error=str(exc),
        )
        emit_text(logger, f"[ERROR] {exc}")
        exit_code = 1
    except KeyboardInterrupt:
        logger.event("run.finish", outcome="interrupted", level="WARNING", provider=args.provider)
        emit_text(logger, "\nInterrupted by user.")
        exit_code = 130
    finally:
        if lock_info:
            lock_path = lock_info["path"]
            try:
                release_run_lock(lock_path)
                logger.event(
                    "run.lock.release",
                    outcome="success",
                    provider=args.provider,
                    lock_path=lock_path,
                )
            except RunLockError as exc:
                logger.event(
                    "run.lock.release",
                    outcome="failed",
                    level="ERROR",
                    provider=args.provider,
                    lock_path=lock_path,
                    error=str(exc),
                )
                emit_text(logger, f"[ERROR] {exc}")
                if exit_code == 0:
                    exit_code = 1
        logger.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
