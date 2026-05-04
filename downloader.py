# pylint: disable=too-many-lines

import argparse
import concurrent.futures
import fnmatch
import getpass
import importlib
import json
import os
import shutil
import sys
import time
import webbrowser

from utils import url_utils
from utils.auth_store import (
    delete_auth_profile,
    delete_profile_secret,
    get_auth_profile,
    get_profile_secret,
    set_auth_profile,
    set_profile_secret,
)
from utils.compatibility import (
    SUPPORTED_PLATFORM_LABELS,
    build_runtime_compatibility_report,
)
from utils.errors import (
    AuthenticationError,
    ProviderConfigurationError,
    ProviderNotImplementedError,
    RemoteAPIError,
    RepoDownloaderError,
    RepositorySyncError,
    RunLockError,
    redact_sensitive_text,
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
    release_run_lock,
    remove_checkpoint,
    repository_matches_filters,
    save_checkpoint,
)
from utils.sentry_utils import capture_exception, initialize_sentry, set_sentry_tags

PROVIDER_CLASS_PATHS = {
    "bitbucket": ("data.source.remote_sources", "BitbucketSource"),
    "github": ("data.source.remote_sources", "GitHubSource"),
    "gitlab": ("data.source.remote_sources", "GitLabSource"),
}
FAILURE_TYPE_ORDER = ("api", "auth", "clone", "fetch", "checkout", "other")
AUTH_PROVIDER_GUIDANCE = {
    "bitbucket": {
        "url": "https://bitbucket.org/account/settings/app-passwords/",
        "credential_label": "app password",
    },
    "github": {
        "url": "https://github.com/settings/tokens",
        "credential_label": "personal access token",
    },
    "gitlab": {
        "url": "https://gitlab.com/-/user_settings/personal_access_tokens",
        "credential_label": "personal access token",
    },
}


def build_parser():
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Download and back up repositories from supported remote providers.",
    )

    parser.add_argument("-u", "--username", type=str, help="Remote account username")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a TOML/YAML config profile.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("backup", "list-backups", "validate-restore", "auth"),
        default="backup",
        help="CLI command to execute.",
    )
    parser.add_argument(
        "auth_provider",
        nargs="?",
        choices=sorted(PROVIDER_CLASS_PATHS.keys()),
        default=None,
        help="Provider name used by the 'auth' command.",
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
        "--auth-profile",
        type=str,
        default="default",
        help="Auth profile name used to load keyring credentials.",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="default",
        help="Auth profile name used by 'auth' commands.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="For 'auth': validate and display current credential status.",
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="For 'auth': remove stored credential and profile metadata.",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="For 'auth': do not open provider credential setup page in browser.",
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
        "--summary-file",
        type=str,
        default=None,
        help="Optional JSON file path to export end-of-run summary metrics.",
    )
    parser.add_argument(
        "--sentry-dsn",
        type=str,
        default=None,
        help="Optional Sentry DSN override (defaults to environment variable).",
    )
    parser.add_argument(
        "--sentry-environment",
        type=str,
        default=None,
        help="Optional Sentry environment override.",
    )
    parser.add_argument(
        "--sentry-release",
        type=str,
        default=None,
        help="Optional Sentry release override.",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help=("Include repository full-name patterns (glob). Can be repeated or comma-separated."),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help=("Exclude repository full-name patterns (glob). Can be repeated or comma-separated."),
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
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent repository sync workers.",
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
    if hasattr(logger, "emit_text"):
        logger.emit_text(message)
        return
    if getattr(logger, "log_format", "text") == "text":
        print(message)


class BufferedLogger:
    def __init__(self, log_format="text"):
        self.log_format = log_format
        self.records = []

    def emit_text(self, message):
        self.records.append(("text", message))

    def event(self, action, outcome="info", level="INFO", message=None, **fields):
        payload = {
            "action": action,
            "outcome": outcome,
            "level": level,
            "message": message,
            "fields": fields,
        }
        self.records.append(("event", payload))
        return payload

    def close(self):
        return None


def flush_buffered_logger(buffered_logger, target_logger):
    for record_type, payload in buffered_logger.records:
        if record_type == "text":
            emit_text(target_logger, payload)
            continue
        target_logger.event(
            payload["action"],
            outcome=payload["outcome"],
            level=payload["level"],
            message=payload["message"],
            **payload["fields"],
        )


def write_summary_report(summary_file, payload):
    summary_path = os.path.expanduser(summary_file)
    summary_directory = os.path.dirname(summary_path)
    if summary_directory:
        os.makedirs(summary_directory, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as summary_handle:
        json.dump(payload, summary_handle, sort_keys=True, indent=2)
        summary_handle.write("\n")
    return summary_path


def _load_toml_config(config_path):
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # Python <3.11
        except ModuleNotFoundError as exc:
            raise ProviderConfigurationError(
                "TOML config requires 'tomli' on Python versions below 3.11."
            ) from exc

    try:
        with open(config_path, "rb") as config_file:
            payload = tomllib.load(config_file)
    except OSError as exc:
        raise ProviderConfigurationError(
            f"Failed reading config file '{config_path}': {exc}"
        ) from exc
    except ValueError as exc:
        raise ProviderConfigurationError(f"Invalid TOML config '{config_path}': {exc}") from exc

    return payload


def _load_yaml_config(config_path):
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ProviderConfigurationError(
            "YAML config requires dependency 'PyYAML'. Install project dependencies."
        ) from exc

    try:
        with open(config_path, encoding="utf-8") as config_file:
            payload = yaml.safe_load(config_file) or {}
    except OSError as exc:
        raise ProviderConfigurationError(
            f"Failed reading config file '{config_path}': {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise ProviderConfigurationError(f"Invalid YAML config '{config_path}': {exc}") from exc

    return payload


def load_config_file(config_path):
    resolved_path = os.path.expanduser(config_path)
    extension = os.path.splitext(resolved_path)[1].lower()
    if extension == ".toml":
        payload = _load_toml_config(resolved_path)
    elif extension in (".yaml", ".yml"):
        payload = _load_yaml_config(resolved_path)
    else:
        raise ProviderConfigurationError("Config file extension must be .toml, .yaml, or .yml.")

    if not isinstance(payload, dict):
        raise ProviderConfigurationError(f"Config file '{resolved_path}' must contain a mapping.")

    backup_section = payload.get("backup")
    if isinstance(backup_section, dict):
        payload = backup_section

    normalized = {}
    for key, value in payload.items():
        normalized[key.replace("-", "_")] = value
    return normalized


def apply_config_defaults(parser, args, config_values):
    repeatable_keys = {"include", "exclude", "branch", "branch_pattern"}
    for key, value in config_values.items():
        if not hasattr(args, key):
            continue
        current_value = getattr(args, key)
        default_value = parser.get_default(key)
        if current_value != default_value:
            continue
        if key in repeatable_keys and isinstance(value, str):
            value = [value]
        setattr(args, key, value)
    return args


def resolve_username(
    username,
    provider,
    auth_profile="default",
    logger=None,
    prompt_if_missing=True,
):
    logger = logger or NullLogger()
    if provider != "bitbucket":
        return username
    if username:
        return username

    profile = get_auth_profile(provider, auth_profile)
    if profile and profile.get("username"):
        stored_username = profile["username"]
        logger.event(
            "auth.username.source",
            outcome="success",
            source="profile",
            auth_profile=auth_profile,
        )
        return stored_username

    if not prompt_if_missing:
        return None

    prompted_username = input("Enter Bitbucket username: ").strip()
    if prompted_username:
        logger.event("auth.username.source", outcome="prompt", source="prompt")
        return prompted_username
    raise ProviderConfigurationError(
        "Bitbucket username is required. Provide '--username' or configure auth profile."
    )


def resolve_token(token_env, provider=None, auth_profile="default", logger=None):
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
            f"Environment variable '{token_env}' was not set. "
            "Falling back to auth profile or prompt."
        )
        logger.event(
            "auth.token.source",
            outcome="fallback",
            level="WARNING",
            token_env=token_env,
            source="fallback",
            message=fallback_msg,
        )
        emit_text(logger, fallback_msg)

    if provider:
        try:
            profile_token = get_profile_secret(provider, auth_profile)
        except ProviderConfigurationError as exc:
            logger.event(
                "auth.token.source",
                outcome="fallback",
                level="WARNING",
                source="prompt",
                auth_profile=auth_profile,
                message=str(exc),
            )
            emit_text(logger, f"[WARN] {exc}")
            profile_token = None
        if profile_token:
            logger.event(
                "auth.token.source",
                outcome="success",
                source="profile",
                auth_profile=auth_profile,
            )
            return profile_token

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


def sanitize_error_text(error, sensitive_values=None):
    return redact_sensitive_text(error, sensitive_values=sensitive_values)


def emit_runtime_compatibility(logger):
    report = build_runtime_compatibility_report()
    logger.event(
        "runtime.compatibility",
        outcome="info",
        python_version=report["python_version"],
        minimum_python_version=report["minimum_python_version"],
        python_supported=report["python_supported"],
        platform=report["platform"],
        platform_supported=report["platform_supported"],
        git_version=report["git_version"],
        minimum_git_version=report["minimum_git_version"],
        git_supported=report["git_supported"],
    )

    if not report["python_supported"]:
        emit_text(
            logger,
            (
                "[WARN] Python runtime is below supported minimum "
                f"({report['python_version']} < {report['minimum_python_version']})."
            ),
        )

    if not report["platform_supported"]:
        supported_platforms = ", ".join(SUPPORTED_PLATFORM_LABELS)
        emit_text(
            logger,
            (
                "[WARN] Runtime platform is outside validated compatibility matrix "
                f"({report['platform']}; supported: {supported_platforms})."
            ),
        )

    if report["git_version"] is None:
        emit_text(
            logger,
            "[WARN] Could not detect git version. Ensure git is installed and available in PATH.",
        )
    elif not report["git_supported"]:
        emit_text(
            logger,
            (
                "[WARN] Git runtime is below supported minimum "
                f"({report['git_version']} < {report['minimum_git_version']})."
            ),
        )

    return report


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


def create_provider_from_values(provider_name, username, token):
    if provider_name not in PROVIDER_CLASS_PATHS:
        raise ProviderConfigurationError(f"Unknown provider '{provider_name}'.")

    if provider_name == "bitbucket" and not username:
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

    return provider_class(username, token)


def create_provider(args, token):
    return create_provider_from_values(args.provider, args.username, token)


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
            f"\t\tChecking out branch {branch_name} {branch_index + 1}/{len(selected_branches)}",
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
            "One or more branch checkout operations failed: " + ", ".join(checkout_failures)
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
    mode_duration_ms = {"mirror": 0, "working": 0}
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
        return "skipped", full_name, mode_duration_ms

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
        return "skipped", full_name, mode_duration_ms

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
        return "skipped", full_name, mode_duration_ms

    paths = build_backup_paths(args.output_dir, args.provider, repo_workspace, repo_name)
    if not args.dry_run:
        os.makedirs(paths["base_dir"], exist_ok=True)
    default_branch_name = get_default_branch_name(extended_repo)
    snapshot_format = getattr(args, "snapshot_format", None)
    snapshot_dir = getattr(args, "snapshot_dir", "./snapshots")
    retain_days = getattr(args, "retain_days", None)
    retain_count = getattr(args, "retain_count", None)

    for mode in selected_modes(args.mode):
        mode_started_at = time.monotonic()
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
        mode_duration_ms[mode] += int((time.monotonic() - mode_started_at) * 1000)

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
    return "success", full_name, mode_duration_ms


def process_repository_with_retries(
    args,
    provider,
    git_source,
    repository_entry,
    index,
    total_repositories,
    logger,
    sensitive_values=None,
):
    repository_for_log = "unknown"
    mode_duration_ms = {"mirror": 0, "working": 0}
    max_attempts = max(1, args.repo_retries + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            outcome, repository_for_log, mode_duration_ms = sync_repository(
                args,
                provider,
                git_source,
                repository_entry,
                index,
                total_repositories,
                logger,
            )
            if outcome == "skipped":
                return {
                    "status": "skipped",
                    "repository": repository_for_log,
                    "mode_duration_ms": mode_duration_ms,
                }
            return {
                "status": "succeeded",
                "repository": repository_for_log,
                "mode_duration_ms": mode_duration_ms,
            }
        except (
            KeyError,
            TypeError,
            ValueError,
            AuthenticationError,
            RemoteAPIError,
            RepositorySyncError,
        ) as exc:
            failure_type = classify_repository_failure(exc)
            sanitized_error = sanitize_error_text(str(exc), sensitive_values=sensitive_values)
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
                    error=sanitized_error,
                )
                emit_text(
                    logger,
                    f"[WARN] Repository failed ({failure_type}), retrying "
                    f"{attempt}/{max_attempts - 1}: {sanitized_error}",
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
                error=sanitized_error,
            )
            emit_text(logger, f"[ERROR] Failed processing repository entry: {sanitized_error}")
            emit_text(logger, "Moving to next repository.")
            return {
                "status": "failed",
                "repository": repository_for_log,
                "failure_type": failure_type,
                "mode_duration_ms": mode_duration_ms,
            }

    return {
        "status": "failed",
        "repository": repository_for_log,
        "failure_type": "other",
        "mode_duration_ms": mode_duration_ms,
    }


def run_backup(args, provider, git_source, logger=None, sensitive_values=None):
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
        "mode_duration_ms": {"mirror": 0, "working": 0},
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

    def checkpoint_success(repository_name):
        if not resume_enabled or not repository_name:
            return
        completed_repositories.add(repository_name)
        checkpoint_payload["completed"] = sorted(completed_repositories)
        try:
            save_checkpoint(checkpoint_path, checkpoint_payload)
        except OSError as exc:
            raise RemoteAPIError(
                f"Failed writing checkpoint state to '{checkpoint_path}': {exc}"
            ) from exc

    def apply_repository_result(result):
        mode_duration = result.get("mode_duration_ms", {})
        for mode in ("mirror", "working"):
            stats["mode_duration_ms"][mode] += mode_duration.get(mode, 0)

        status = result.get("status")
        if status == "skipped":
            stats["skipped"] += 1
            return
        if status == "succeeded":
            stats["succeeded"] += 1
            checkpoint_success(result.get("repository"))
            return
        stats["failed"] += 1
        failure_type = result.get("failure_type", "other")
        stats["failure_types"][failure_type] += 1

    pending_repositories = []
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
        pending_repositories.append((index, repository_entry))

    worker_count = max(1, getattr(args, "workers", 1))
    if worker_count > 1 and len(pending_repositories) > 1:
        logger.event(
            "repositories.concurrent",
            outcome="enabled",
            provider=args.provider,
            mode=args.mode,
            workers=worker_count,
            queued_count=len(pending_repositories),
        )
        result_by_index = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {}
            for index, repository_entry in pending_repositories:
                buffered_logger = BufferedLogger(log_format=logger.log_format)
                future = executor.submit(
                    process_repository_with_retries,
                    args,
                    provider,
                    git_source,
                    repository_entry,
                    index,
                    len(repositories),
                    buffered_logger,
                    sensitive_values,
                )
                future_map[future] = (index, buffered_logger)

            for future, metadata in future_map.items():
                index, buffered_logger = metadata
                result_by_index[index] = (future.result(), buffered_logger)

        for index in sorted(result_by_index):
            result, buffered_logger = result_by_index[index]
            flush_buffered_logger(buffered_logger, logger)
            apply_repository_result(result)
    else:
        for index, repository_entry in pending_repositories:
            result = process_repository_with_retries(
                args,
                provider,
                git_source,
                repository_entry,
                index,
                len(repositories),
                logger,
                sensitive_values,
            )
            apply_repository_result(result)

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
        repo_class = git_module.Repo
        git_exc_module = importlib.import_module("git.exc")
        git_error_class = git_exc_module.GitError
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


def _extract_user_hint(user_info):
    if not isinstance(user_info, dict):
        return "unknown"
    for key in ("username", "login", "name", "email"):
        value = user_info.get(key)
        if value:
            return str(value)
    if user_info.get("id") is not None:
        return str(user_info["id"])
    return "unknown"


def _emit_auth_guidance(provider_name, no_open_browser):
    guidance = AUTH_PROVIDER_GUIDANCE.get(provider_name, {})
    setup_url = guidance.get("url")
    credential_label = guidance.get("credential_label", "token")
    print(
        f"Auth setup for '{provider_name}': create a {credential_label} and paste it when prompted."
    )
    if setup_url:
        print(f"Provider setup URL: {setup_url}")
        if not no_open_browser:
            try:
                webbrowser.open(setup_url, new=2)
            except webbrowser.Error:
                pass


def run_auth_command(args):  # pylint: disable=too-many-return-statements
    provider_name = args.auth_provider or args.provider
    profile_name = args.profile or "default"

    if provider_name not in PROVIDER_CLASS_PATHS:
        print(
            f"[ERROR] Provider is required for auth command. "
            f"Use one of: {', '.join(sorted(PROVIDER_CLASS_PATHS.keys()))}."
        )
        return 1

    if args.status and args.logout:
        print("[ERROR] Use only one of --status or --logout for auth command.")
        return 1

    try:
        if args.logout:
            removed_secret = delete_profile_secret(provider_name, profile_name)
            removed_profile = delete_auth_profile(provider_name, profile_name)
            if removed_secret or removed_profile:
                print(f"Auth profile removed: provider={provider_name}, profile={profile_name}")
            else:
                print(
                    "No stored auth profile found to remove: "
                    f"provider={provider_name}, profile={profile_name}"
                )
            return 0

        if args.status:
            token = get_profile_secret(provider_name, profile_name)
            if not token:
                print(
                    "[ERROR] No stored credential found. "
                    f"Run `repo-downloader auth {provider_name} --profile {profile_name}` first."
                )
                return 1

            username = resolve_username(
                args.username,
                provider_name,
                auth_profile=profile_name,
                prompt_if_missing=False,
            )
            provider = create_provider_from_values(provider_name, username, token)
            if not provider.auth_ok():
                message = provider.auth_error or "Unknown authentication error."
                print(
                    f"[ERROR] Auth profile validation failed for provider={provider_name}, "
                    f"profile={profile_name}: {message}"
                )
                return 1

            user_hint = _extract_user_hint(getattr(provider, "current_user", None))
            print(
                f"Auth profile is valid: provider={provider_name}, profile={profile_name}, "
                f"user={user_hint}"
            )
            return 0

        _emit_auth_guidance(provider_name, args.no_open_browser)
        username = resolve_username(
            args.username,
            provider_name,
            auth_profile=profile_name,
            prompt_if_missing=(provider_name == "bitbucket"),
        )
        token = getpass.getpass("Enter account token / app password: ").strip()
        if not token:
            print("[ERROR] Empty credential value. Auth setup aborted.")
            return 1

        provider = create_provider_from_values(provider_name, username, token)
        if not provider.auth_ok():
            message = provider.auth_error or "Unknown authentication error."
            print(f"[ERROR] Authentication failed: {sanitize_error_text(message, [token])}")
            return 1

        user_hint = _extract_user_hint(getattr(provider, "current_user", None))
        set_profile_secret(provider_name, profile_name, token)
        set_auth_profile(
            provider_name,
            profile_name,
            username=username,
            user_hint=user_hint,
        )
        print(
            "Authentication stored successfully: "
            f"provider={provider_name}, profile={profile_name}, user={user_hint}"
        )
        return 0
    except RepoDownloaderError as exc:
        print(f"[ERROR] {exc}")
        return 1


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.config:
        config_values = load_config_file(args.config)
        args = apply_config_defaults(parser, args, config_values)

    if args.command == "auth" and not args.auth_provider:
        parser.error(
            "auth command requires provider positional argument (bitbucket|github|gitlab)."
        )
    if args.command != "auth" and args.auth_provider:
        parser.error(
            "Positional provider argument is only valid for the auth command. "
            "Use --provider for backup/list-backups/validate-restore commands."
        )

    if args.command in ("auth", "list-backups", "validate-restore"):
        provider_for_tags = args.auth_provider if args.command == "auth" else args.provider
        initialize_sentry(args=args, logger=None)
        set_sentry_tags(
            command=args.command,
            provider=provider_for_tags,
            mode=args.mode,
            run_id=None,
        )
        try:
            if args.command == "auth":
                return run_auth_command(args)
            if args.command == "list-backups":
                return run_list_backups_command(args)
            return run_validate_restore_command(args)
        except Exception as exc:  # pragma: no cover  # pylint: disable=broad-exception-caught
            capture_exception(exc)
            print(f"[ERROR] {sanitize_error_text(str(exc))}")
            return 1

    if args.repo_retries < 0:
        parser.error("--repo-retries must be zero or a positive integer.")
    if args.workers < 1:
        parser.error("--workers must be a positive integer.")
    if args.retain_days is not None and args.retain_days < 0:
        parser.error("--retain-days must be zero or a positive integer.")
    if args.retain_count is not None and args.retain_count < 0:
        parser.error("--retain-count must be zero or a positive integer.")
    args.include = normalize_repo_patterns(args.include)
    args.exclude = normalize_repo_patterns(args.exclude)
    args.branch_names = normalize_cli_list(args.branch)
    args.branch_patterns = normalize_cli_list(args.branch_pattern)
    logger = RunLogger(log_format=args.log_format, log_file=args.log_file)
    sentry_state = initialize_sentry(args=args, logger=logger)
    set_sentry_tags(
        command=args.command,
        provider=args.provider,
        mode=args.mode,
        run_id=logger.run_id,
    )

    logger.event(
        "run.start",
        outcome="start",
        command=args.command,
        config=args.config,
        provider=args.provider,
        mode=args.mode,
        workspace=args.workspace,
        output_dir=os.path.expanduser(args.output_dir),
        snapshot_format=args.snapshot_format,
        snapshot_dir=os.path.expanduser(args.snapshot_dir),
        summary_file=args.summary_file,
        dry_run=args.dry_run,
        include_archived=args.include_archived,
        ssh_key_path=args.ssh_key_path,
        token_env=args.token_env,
        auth_profile=args.auth_profile,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        branch_names=args.branch_names,
        branch_patterns=args.branch_patterns,
        default_branch_only=args.default_branch_only,
        repo_retries=args.repo_retries,
        workers=args.workers,
        retain_days=args.retain_days,
        retain_count=args.retain_count,
        force_lock=args.force_lock,
        resume=args.resume,
        sentry_enabled=sentry_state["enabled"],
        log_format=args.log_format,
    )
    compatibility_report = emit_runtime_compatibility(logger)

    lock_info = None
    exit_code = 1
    sensitive_values = []
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
        token = resolve_token(
            args.token_env,
            provider=args.provider,
            auth_profile=args.auth_profile,
            logger=logger,
        )
        sensitive_values.append(token)
        args.username = resolve_username(
            args.username,
            args.provider,
            auth_profile=args.auth_profile,
            logger=logger,
        )
        provider = create_provider(args, token)
        if not provider.auth_ok():
            message = provider.auth_error or "Unknown authentication error."
            if "not implemented" in message.lower():
                raise ProviderNotImplementedError(message)
            raise AuthenticationError(message)

        try:
            git_module = importlib.import_module("data.source.git_source")
            git_source_class = git_module.GitSource
        except ModuleNotFoundError as exc:
            raise ProviderConfigurationError(
                f"Missing dependency '{exc.name}' required for git operations. "
                "Install project dependencies with `pip install -r requirements.txt`."
            ) from exc

        git_source = git_source_class(key_path=args.ssh_key_path)
        stats = run_backup(
            args,
            provider,
            git_source,
            logger=logger,
            sensitive_values=sensitive_values,
        )
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
            mode_duration_ms=stats["mode_duration_ms"],
        )
        summary_payload = {
            "provider": args.provider,
            "mode": args.mode,
            "processed": stats["processed"],
            "succeeded": stats["succeeded"],
            "skipped": stats["skipped"],
            "failed": stats["failed"],
            "failure_types": stats["failure_types"],
            "mode_duration_ms": stats["mode_duration_ms"],
            "exit_code": exit_code,
            "compatibility": compatibility_report,
        }
        if args.summary_file:
            try:
                summary_path = write_summary_report(args.summary_file, summary_payload)
            except (OSError, TypeError, ValueError) as exc:
                raise ProviderConfigurationError(
                    f"Failed writing summary file '{args.summary_file}': {exc}"
                ) from exc
            logger.event(
                "run.summary.write",
                outcome="success",
                provider=args.provider,
                mode=args.mode,
                path=summary_path,
            )
        emit_text(
            logger,
            "All repos finished! "
            f"processed={stats['processed']}, succeeded={stats['succeeded']}, "
            f"skipped={stats['skipped']}, failed={stats['failed']}, "
            f"failure_types={format_failure_counters(stats['failure_types'])}, "
            f"mode_duration_ms={stats['mode_duration_ms']}",
        )
    except RepoDownloaderError as exc:
        sanitized_error = sanitize_error_text(str(exc), sensitive_values=sensitive_values)
        logger.event(
            "run.finish",
            outcome="failed",
            level="ERROR",
            provider=args.provider,
            error=sanitized_error,
        )
        emit_text(logger, f"[ERROR] {sanitized_error}")
        exit_code = 1
        capture_exception(exc)
    except Exception as exc:  # pragma: no cover  # pylint: disable=broad-exception-caught
        capture_exception(exc)
        sanitized_error = sanitize_error_text(str(exc), sensitive_values=sensitive_values)
        logger.event(
            "run.finish",
            outcome="failed",
            level="ERROR",
            provider=args.provider,
            error=sanitized_error,
        )
        emit_text(logger, f"[ERROR] {sanitized_error}")
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
                sanitized_error = sanitize_error_text(str(exc), sensitive_values=sensitive_values)
                logger.event(
                    "run.lock.release",
                    outcome="failed",
                    level="ERROR",
                    provider=args.provider,
                    lock_path=lock_path,
                    error=sanitized_error,
                )
                emit_text(logger, f"[ERROR] {sanitized_error}")
                if exit_code == 0:
                    exit_code = 1
        logger.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
