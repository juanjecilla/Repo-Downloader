import fnmatch
import json
import os
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
        with open(lock_path, "r", encoding="utf-8") as lock_file:
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
    if os.path.exists(lock_path):
        existing_lock = _read_lock_metadata(lock_path)
        existing_pid = existing_lock.get("pid")
        existing_run_id = existing_lock.get("run_id")
        if is_process_running(existing_pid):
            if not force_lock:
                raise RunLockError(
                    "Another backup run is active for this output root "
                    f"(provider={provider}, pid={existing_pid}, run_id={existing_run_id}). "
                    "Use --force-lock to replace the existing lock."
                )
            replaced_forced = True
        else:
            replaced_stale = True

        try:
            os.remove(lock_path)
        except OSError as exc:
            raise RunLockError(
                f"Unable to replace existing run lock '{lock_path}': {exc}"
            ) from exc

    lock_payload = {
        "pid": os.getpid(),
        "provider": provider,
        "run_id": run_id,
        "created_at": utc_now_iso(),
    }
    try:
        with open(lock_path, "w", encoding="utf-8") as lock_file:
            json.dump(lock_payload, lock_file, sort_keys=True)
            lock_file.write("\n")
    except OSError as exc:
        raise RunLockError(f"Unable to create run lock '{lock_path}': {exc}") from exc

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
