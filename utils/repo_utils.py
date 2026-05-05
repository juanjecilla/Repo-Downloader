import fnmatch
import json
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from utils.errors import RunLockError


def extract_workspace_and_name(full_name: str) -> Tuple[str, str]:
    parts = full_name.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid repository full name: {full_name!r}")
    return parts[0], parts[1]


def parse_repository_entry(repository_entry: Dict) -> Dict:
    """Normalize repository entries returned by providers."""
    repository = repository_entry.get("repository", repository_entry)
    if "full_name" not in repository:
        raise KeyError("Repository entry does not include 'full_name'")

    workspace, name = extract_workspace_and_name(repository["full_name"])
    return {
        "workspace": workspace,
        "name": name,
        "full_name": repository["full_name"],
        "repository": repository,
    }


def filter_repositories_by_workspace(
    repositories: List[Dict],
    workspace: Optional[str],
) -> List[Dict]:
    if not workspace:
        return repositories

    normalized_workspace = workspace.lower()
    filtered = []
    for entry in repositories:
        repository = entry.get("repository", entry)
        full_name = repository.get("full_name", "")
        if full_name.lower().startswith(f"{normalized_workspace}/"):
            filtered.append(entry)
    return filtered


def is_archived_repository(
    summary_repository: Dict,
    extended_repository: Optional[Dict] = None,
) -> bool:
    candidates = [summary_repository]
    if extended_repository:
        candidates.append(extended_repository)

    for candidate in candidates:
        if candidate.get("is_archived") is True:
            return True
        if candidate.get("archived") is True:
            return True
        if isinstance(candidate.get("repository"), dict):
            nested = candidate["repository"]
            if nested.get("is_archived") is True or nested.get("archived") is True:
                return True
    return False


def build_backup_paths(
    output_dir: str,
    provider: str,
    workspace: str,
    repository_name: str,
) -> Dict[str, str]:
    output_root = os.path.expanduser(output_dir)
    base_dir = os.path.join(output_root, provider, workspace)
    return {
        "base_dir": base_dir,
        "mirror_path": os.path.join(base_dir, f"{repository_name}.git"),
        "working_path": os.path.join(base_dir, repository_name),
    }


def snapshot_timestamp(now: Optional[datetime] = None) -> str:
    timestamp = now or datetime.now(timezone.utc)
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def build_snapshot_path(
    snapshot_dir: str,
    provider: str,
    workspace: str,
    repository_name: str,
    snapshot_format: str,
    timestamp: Optional[str] = None,
) -> str:
    normalized_timestamp = timestamp or snapshot_timestamp()
    output_root = os.path.expanduser(snapshot_dir)
    snapshot_base = os.path.join(
        output_root,
        provider,
        workspace,
        f"{repository_name}-{normalized_timestamp}",
    )
    if snapshot_format == "zip":
        return f"{snapshot_base}.zip"
    if snapshot_format == "tar.gz":
        return f"{snapshot_base}.tar.gz"
    raise ValueError(f"Unsupported snapshot format: {snapshot_format!r}")


def create_snapshot_archive(source_path: str, snapshot_path: str, snapshot_format: str) -> str:
    snapshot_directory = os.path.dirname(snapshot_path)
    os.makedirs(snapshot_directory, exist_ok=True)
    source_parent = os.path.dirname(source_path)
    source_name = os.path.basename(source_path)

    if snapshot_format == "zip":
        archive_base = snapshot_path[: -len(".zip")]
        created_path = shutil.make_archive(
            base_name=archive_base,
            format="zip",
            root_dir=source_parent,
            base_dir=source_name,
        )
        return created_path

    if snapshot_format == "tar.gz":
        archive_base = snapshot_path[: -len(".tar.gz")]
        created_path = shutil.make_archive(
            base_name=archive_base,
            format="gztar",
            root_dir=source_parent,
            base_dir=source_name,
        )
        return created_path

    raise ValueError(f"Unsupported snapshot format: {snapshot_format!r}")


def collect_snapshot_paths(
    snapshot_dir: str,
    provider: str,
    workspace: str,
    repository_name: str,
) -> List[str]:
    snapshot_root = os.path.expanduser(snapshot_dir)
    workspace_dir = os.path.join(snapshot_root, provider, workspace)
    if not os.path.isdir(workspace_dir):
        return []

    snapshot_paths = []
    prefix = f"{repository_name}-"
    for entry in os.listdir(workspace_dir):
        if not entry.startswith(prefix):
            continue
        if not (entry.endswith(".zip") or entry.endswith(".tar.gz")):
            continue
        full_path = os.path.join(workspace_dir, entry)
        if os.path.isfile(full_path):
            snapshot_paths.append(full_path)
    return snapshot_paths


def plan_retention_deletions(
    paths: List[str],
    retain_days: Optional[int] = None,
    retain_count: Optional[int] = None,
    now_timestamp: Optional[float] = None,
) -> List[str]:
    if retain_days is None and retain_count is None:
        return []

    normalized = []
    for path in paths:
        try:
            modified_at = os.path.getmtime(path)
        except OSError:
            continue
        normalized.append((path, modified_at))

    normalized.sort(key=lambda item: item[1], reverse=True)
    deletions = set()

    if retain_days is not None:
        reference = now_timestamp if now_timestamp is not None else time.time()
        cutoff = reference - (retain_days * 86400)
        for path, modified_at in normalized:
            if modified_at < cutoff:
                deletions.add(path)

    if retain_count is not None:
        for index, (path, _modified_at) in enumerate(normalized):
            if index >= retain_count:
                deletions.add(path)

    return [path for path, _modified_at in normalized if path in deletions]


def delete_artifact_path(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
        return
    os.remove(path)


def build_checkpoint_path(output_dir: str, provider: str) -> str:
    output_root = os.path.expanduser(output_dir)
    return os.path.join(output_root, provider, ".repo-downloader-checkpoint.json")


def load_checkpoint(checkpoint_path: str) -> Dict:
    if not os.path.isfile(checkpoint_path):
        return {}

    try:
        with open(checkpoint_path, encoding="utf-8") as checkpoint_file:
            payload = json.load(checkpoint_file)
            if isinstance(payload, dict):
                return payload
    except (OSError, ValueError, TypeError):
        return {}
    return {}


def save_checkpoint(checkpoint_path: str, payload: Dict) -> None:
    checkpoint_dir = os.path.dirname(checkpoint_path)
    os.makedirs(checkpoint_dir, exist_ok=True)

    temp_path = f"{checkpoint_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as checkpoint_file:
        json.dump(payload, checkpoint_file, sort_keys=True)
        checkpoint_file.write("\n")
    os.replace(temp_path, checkpoint_path)


def remove_checkpoint(checkpoint_path: str) -> None:
    try:
        os.remove(checkpoint_path)
    except FileNotFoundError:
        return


def normalize_repo_patterns(raw_patterns: Optional[List[str]]) -> List[str]:
    """Normalize include/exclude patterns from CLI values."""
    normalized: List[str] = []
    if not raw_patterns:
        return normalized

    for raw_pattern in raw_patterns:
        for part in raw_pattern.split(","):
            cleaned = part.strip().lower()
            if cleaned:
                normalized.append(cleaned)
    return normalized


def repository_matches_filters(
    full_name: str,
    include_patterns: Optional[List[str]],
    exclude_patterns: Optional[List[str]],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Evaluate include/exclude pattern filtering for a repository."""
    normalized_full_name = full_name.lower()
    include = [pattern.lower() for pattern in (include_patterns or [])]
    exclude = [pattern.lower() for pattern in (exclude_patterns or [])]

    if include and not any(
        fnmatch.fnmatchcase(normalized_full_name, pattern) for pattern in include
    ):
        detail = "does not match include patterns"
        return False, "include_miss", detail

    for pattern in exclude:
        if fnmatch.fnmatchcase(normalized_full_name, pattern):
            detail = f"matches exclude pattern '{pattern}'"
            return False, "exclude_match", detail

    return True, None, None


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def build_run_lock_path(output_dir: str, provider: str) -> str:
    output_root = os.path.expanduser(output_dir)
    lock_name = f".repo-downloader-{provider}.lock"
    return os.path.join(output_root, lock_name)


def _read_lock_metadata(lock_path: str) -> Dict:
    try:
        with open(lock_path, encoding="utf-8") as lock_file:
            payload = json.load(lock_file)
            if isinstance(payload, dict):
                return payload
    except (OSError, ValueError, TypeError):
        return {}
    return {}


def is_process_running(pid: Optional[int]) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_run_lock(
    output_dir: str,
    provider: str,
    run_id: str,
    force_lock: bool = False,
) -> Dict[str, object]:
    lock_path = build_run_lock_path(output_dir, provider)
    output_root = os.path.dirname(lock_path)
    os.makedirs(output_root, exist_ok=True)

    replaced_stale = False
    replaced_forced = False

    lock_payload = {
        "pid": os.getpid(),
        "provider": provider,
        "run_id": run_id,
        "created_at": utc_now_iso(),
    }
    while True:
        try:
            with open(lock_path, "x", encoding="utf-8") as lock_file:
                json.dump(lock_payload, lock_file, sort_keys=True)
                lock_file.write("\n")
            break
        except FileExistsError as exists_error:
            existing_lock = _read_lock_metadata(lock_path)
            existing_pid = existing_lock.get("pid")
            existing_run_id = existing_lock.get("run_id")
            if is_process_running(existing_pid):
                if not force_lock:
                    raise RunLockError(
                        "Another backup run is active for this output root "
                        f"(provider={provider}, pid={existing_pid}, run_id={existing_run_id}). "
                        "Use --force-lock to replace the existing lock."
                    ) from exists_error
                replaced_forced = True
            else:
                replaced_stale = True

            try:
                os.remove(lock_path)
            except FileNotFoundError:
                # Another process changed the lock while we were resolving it; retry.
                continue
            except OSError as remove_error:
                raise RunLockError(
                    f"Unable to replace existing run lock '{lock_path}': {remove_error}"
                ) from remove_error
        except OSError as create_error:
            raise RunLockError(
                f"Unable to create run lock '{lock_path}': {create_error}"
            ) from create_error

    return {
        "path": lock_path,
        "replaced_stale": replaced_stale,
        "replaced_forced": replaced_forced,
    }


def release_run_lock(lock_path: str) -> None:
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RunLockError(f"Unable to remove run lock '{lock_path}': {exc}") from exc
