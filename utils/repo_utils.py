import os
from typing import Dict, List, Optional, Tuple


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


def filter_repositories_by_workspace(repositories: List[Dict], workspace: Optional[str]) -> List[Dict]:
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


def is_archived_repository(summary_repository: Dict, extended_repository: Optional[Dict] = None) -> bool:
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


def build_backup_paths(output_dir: str, provider: str, workspace: str, repository_name: str) -> Dict[str, str]:
    output_root = os.path.expanduser(output_dir)
    base_dir = os.path.join(output_root, provider, workspace)
    return {
        "base_dir": base_dir,
        "mirror_path": os.path.join(base_dir, f"{repository_name}.git"),
        "working_path": os.path.join(base_dir, repository_name),
    }
