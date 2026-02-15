import json
import os
import tempfile
import unittest
from unittest.mock import patch

from utils.repo_utils import (
    acquire_run_lock,
    build_backup_paths,
    build_run_lock_path,
    extract_workspace_and_name,
    filter_repositories_by_workspace,
    is_archived_repository,
    is_process_running,
    normalize_repo_patterns,
    parse_repository_entry,
    release_run_lock,
    repository_matches_filters,
)
from utils.errors import RunLockError


class TestRepoUtils(unittest.TestCase):
    def test_extract_workspace_and_name(self):
        workspace, repo_name = extract_workspace_and_name("acme/my-repo")
        self.assertEqual("acme", workspace)
        self.assertEqual("my-repo", repo_name)

    def test_extract_workspace_and_name_invalid(self):
        with self.assertRaises(ValueError):
            extract_workspace_and_name("invalid")

    def test_parse_repository_entry_nested(self):
        parsed = parse_repository_entry({"repository": {"full_name": "acme/my-repo"}})
        self.assertEqual("acme", parsed["workspace"])
        self.assertEqual("my-repo", parsed["name"])

    def test_filter_repositories_by_workspace(self):
        repositories = [
            {"repository": {"full_name": "acme/one"}},
            {"repository": {"full_name": "other/two"}},
        ]
        filtered = filter_repositories_by_workspace(repositories, "acme")
        self.assertEqual(1, len(filtered))
        self.assertEqual("acme/one", filtered[0]["repository"]["full_name"])

    def test_is_archived_repository_checks_summary_and_extended(self):
        summary = {"full_name": "acme/repo", "is_archived": False}
        extended = {"full_name": "acme/repo", "archived": True}
        self.assertTrue(is_archived_repository(summary, extended))

    def test_build_backup_paths(self):
        paths = build_backup_paths("./backups", "bitbucket", "acme", "repo")
        self.assertEqual("./backups/bitbucket/acme", paths["base_dir"])
        self.assertEqual("./backups/bitbucket/acme/repo.git", paths["mirror_path"])
        self.assertEqual("./backups/bitbucket/acme/repo", paths["working_path"])

    def test_normalize_repo_patterns_expands_comma_values(self):
        patterns = normalize_repo_patterns(["acme/*, other/*", "team/repo"])
        self.assertEqual(["acme/*", "other/*", "team/repo"], patterns)

    def test_normalize_repo_patterns_lowercases_values(self):
        patterns = normalize_repo_patterns(["Acme/*, TEAM/Repo"])
        self.assertEqual(["acme/*", "team/repo"], patterns)

    def test_repository_matches_filters_no_filters(self):
        matches, reason, detail = repository_matches_filters(
            full_name="acme/repo-one",
            include_patterns=[],
            exclude_patterns=[],
        )
        self.assertTrue(matches)
        self.assertIsNone(reason)
        self.assertIsNone(detail)

    def test_repository_matches_filters_exclude_only_match(self):
        matches, reason, detail = repository_matches_filters(
            full_name="acme/repo-one",
            include_patterns=[],
            exclude_patterns=["other/*"],
        )
        self.assertTrue(matches)
        self.assertIsNone(reason)
        self.assertIsNone(detail)

    def test_repository_matches_filters_exact_pattern_match(self):
        matches, reason, detail = repository_matches_filters(
            full_name="acme/specific-repo",
            include_patterns=["acme/specific-repo"],
            exclude_patterns=[],
        )
        self.assertTrue(matches)
        self.assertIsNone(reason)
        self.assertIsNone(detail)

    def test_repository_matches_filters_case_insensitive(self):
        matches, reason, detail = repository_matches_filters(
            full_name="AcMe/Repo-One",
            include_patterns=["acme/*"],
            exclude_patterns=["ACME/private-*"],
        )
        self.assertTrue(matches)
        self.assertIsNone(reason)
        self.assertIsNone(detail)

    def test_repository_matches_filters_include_miss(self):
        matches, reason, detail = repository_matches_filters(
            full_name="acme/repo-one",
            include_patterns=["other/*"],
            exclude_patterns=[],
        )
        self.assertFalse(matches)
        self.assertEqual("include_miss", reason)
        self.assertEqual("does not match include patterns", detail)

    def test_repository_matches_filters_exclude_match(self):
        matches, reason, detail = repository_matches_filters(
            full_name="acme/repo-one",
            include_patterns=["acme/*"],
            exclude_patterns=["acme/repo-*"],
        )
        self.assertFalse(matches)
        self.assertEqual("exclude_match", reason)
        self.assertIn("matches exclude pattern", detail)

    def test_repository_matches_filters_include_then_exclude_precedence(self):
        matches, reason, detail = repository_matches_filters(
            full_name="acme/repo-one",
            include_patterns=["acme/*"],
            exclude_patterns=["other/*"],
        )
        self.assertTrue(matches)
        self.assertIsNone(reason)
        self.assertIsNone(detail)

    def test_acquire_and_release_run_lock(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_info = acquire_run_lock(
                output_dir=tmp_dir,
                provider="bitbucket",
                run_id="run-test",
                force_lock=False,
            )
            self.assertTrue(os.path.exists(lock_info["path"]))
            self.assertFalse(lock_info["replaced_stale"])
            self.assertFalse(lock_info["replaced_forced"])

            release_run_lock(lock_info["path"])
            self.assertFalse(os.path.exists(lock_info["path"]))

    def test_acquire_run_lock_replaces_stale_lock(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = build_run_lock_path(tmp_dir, "bitbucket")
            with open(lock_path, "w", encoding="utf-8") as lock_file:
                json.dump({"pid": 999999, "provider": "bitbucket", "run_id": "old"}, lock_file)

            lock_info = acquire_run_lock(
                output_dir=tmp_dir,
                provider="bitbucket",
                run_id="run-test",
                force_lock=False,
            )
            self.assertTrue(lock_info["replaced_stale"])
            self.assertFalse(lock_info["replaced_forced"])
            release_run_lock(lock_info["path"])

    def test_acquire_run_lock_rejects_active_lock_without_force(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = build_run_lock_path(tmp_dir, "bitbucket")
            with open(lock_path, "w", encoding="utf-8") as lock_file:
                json.dump(
                    {"pid": os.getpid(), "provider": "bitbucket", "run_id": "active-run"},
                    lock_file,
                )

            with self.assertRaises(RunLockError):
                acquire_run_lock(
                    output_dir=tmp_dir,
                    provider="bitbucket",
                    run_id="run-test",
                    force_lock=False,
                )

    def test_acquire_run_lock_force_replaces_active_lock(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = build_run_lock_path(tmp_dir, "bitbucket")
            with open(lock_path, "w", encoding="utf-8") as lock_file:
                json.dump(
                    {"pid": os.getpid(), "provider": "bitbucket", "run_id": "active-run"},
                    lock_file,
                )

            with patch("utils.repo_utils.is_process_running", return_value=True):
                lock_info = acquire_run_lock(
                    output_dir=tmp_dir,
                    provider="bitbucket",
                    run_id="run-test",
                    force_lock=True,
                )
            self.assertFalse(lock_info["replaced_stale"])
            self.assertTrue(lock_info["replaced_forced"])
            release_run_lock(lock_info["path"])

    def test_extract_workspace_and_name_with_multiple_slashes(self):
        workspace, name = extract_workspace_and_name("acme/sub/repo-name")
        self.assertEqual("acme", workspace)
        self.assertEqual("sub/repo-name", name)

    def test_extract_workspace_and_name_with_special_characters(self):
        workspace, name = extract_workspace_and_name("my-workspace/my_repo.git")
        self.assertEqual("my-workspace", workspace)
        self.assertEqual("my_repo.git", name)

    def test_parse_repository_entry_handles_direct_repository_format(self):
        parsed = parse_repository_entry({"full_name": "acme/repo"})
        self.assertEqual("acme", parsed["workspace"])
        self.assertEqual("repo", parsed["name"])
        self.assertEqual("acme/repo", parsed["full_name"])

    def test_parse_repository_entry_raises_key_error_for_missing_full_name(self):
        with self.assertRaises(KeyError):
            parse_repository_entry({"name": "repo"})

    def test_filter_repositories_by_workspace_case_insensitive(self):
        repositories = [
            {"repository": {"full_name": "ACME/one"}},
            {"repository": {"full_name": "other/two"}},
        ]
        filtered = filter_repositories_by_workspace(repositories, "acme")
        self.assertEqual(1, len(filtered))

    def test_filter_repositories_by_workspace_with_none_returns_all(self):
        repositories = [
            {"repository": {"full_name": "acme/one"}},
            {"repository": {"full_name": "other/two"}},
        ]
        filtered = filter_repositories_by_workspace(repositories, None)
        self.assertEqual(2, len(filtered))

    def test_filter_repositories_by_workspace_handles_empty_list(self):
        filtered = filter_repositories_by_workspace([], "acme")
        self.assertEqual(0, len(filtered))

    def test_is_archived_repository_checks_is_archived_field(self):
        summary = {"full_name": "acme/repo", "is_archived": True}
        self.assertTrue(is_archived_repository(summary))

    def test_is_archived_repository_checks_archived_field(self):
        summary = {"full_name": "acme/repo", "archived": True}
        self.assertTrue(is_archived_repository(summary))

    def test_is_archived_repository_checks_nested_repository_field(self):
        summary = {"repository": {"full_name": "acme/repo", "is_archived": True}}
        self.assertTrue(is_archived_repository(summary))

    def test_is_archived_repository_returns_false_when_not_archived(self):
        summary = {"full_name": "acme/repo", "is_archived": False}
        extended = {"full_name": "acme/repo", "archived": False}
        self.assertFalse(is_archived_repository(summary, extended))

    def test_is_archived_repository_extended_overrides_summary(self):
        summary = {"full_name": "acme/repo", "is_archived": False}
        extended = {"full_name": "acme/repo", "archived": True}
        self.assertTrue(is_archived_repository(summary, extended))

    def test_build_backup_paths_expands_tilde(self):
        paths = build_backup_paths("~/backups", "github", "acme", "repo")
        expected_base = os.path.expanduser("~/backups/github/acme")
        self.assertEqual(expected_base, paths["base_dir"])

    def test_build_backup_paths_handles_trailing_slash(self):
        paths = build_backup_paths("./backups/", "bitbucket", "acme", "repo")
        self.assertTrue(paths["base_dir"].endswith("bitbucket/acme"))

    def test_normalize_repo_patterns_handles_empty_input(self):
        patterns = normalize_repo_patterns([])
        self.assertEqual([], patterns)

    def test_normalize_repo_patterns_handles_mixed_case(self):
        patterns = normalize_repo_patterns(["ACME/*", "Other/REPO"])
        self.assertEqual(["acme/*", "other/repo"], patterns)

    def test_repository_matches_filters_handles_multiple_include_patterns(self):
        matches, _, _ = repository_matches_filters(
            full_name="acme/repo",
            include_patterns=["acme/*", "other/*"],
            exclude_patterns=[],
        )
        self.assertTrue(matches)

    def test_repository_matches_filters_handles_multiple_exclude_patterns(self):
        matches, reason, _ = repository_matches_filters(
            full_name="acme/private-repo",
            include_patterns=["acme/*"],
            exclude_patterns=["acme/private-*", "acme/secret-*"],
        )
        self.assertFalse(matches)
        self.assertEqual("exclude_match", reason)

    def test_repository_matches_filters_with_wildcard_pattern(self):
        matches, _, _ = repository_matches_filters(
            full_name="acme/repo",
            include_patterns=["*"],
            exclude_patterns=[],
        )
        self.assertTrue(matches)

    def test_build_run_lock_path_includes_provider_name(self):
        lock_path = build_run_lock_path("/tmp/backups", "github")
        self.assertIn("github", lock_path)
        self.assertTrue(lock_path.endswith(".lock"))

    def test_is_process_running_returns_false_for_invalid_pid(self):
        self.assertFalse(is_process_running(None))
        self.assertFalse(is_process_running(0))
        self.assertFalse(is_process_running(-1))

    def test_is_process_running_returns_true_for_current_process(self):
        self.assertTrue(is_process_running(os.getpid()))

    def test_is_process_running_returns_false_for_nonexistent_pid(self):
        self.assertFalse(is_process_running(999999))

    def test_release_run_lock_does_not_raise_for_missing_lock(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = os.path.join(tmp_dir, "nonexistent.lock")
            release_run_lock(lock_path)

    def test_acquire_run_lock_creates_valid_json_metadata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_info = acquire_run_lock(
                output_dir=tmp_dir,
                provider="bitbucket",
                run_id="test-run",
                force_lock=False,
            )
            with open(lock_info["path"], "r", encoding="utf-8") as lock_file:
                metadata = json.load(lock_file)

            self.assertEqual(os.getpid(), metadata["pid"])
            self.assertEqual("bitbucket", metadata["provider"])
            self.assertEqual("test-run", metadata["run_id"])
            self.assertIn("created_at", metadata)

            release_run_lock(lock_info["path"])

    def test_acquire_run_lock_handles_corrupted_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = build_run_lock_path(tmp_dir, "bitbucket")
            with open(lock_path, "w", encoding="utf-8") as lock_file:
                lock_file.write("invalid json content")

            lock_info = acquire_run_lock(
                output_dir=tmp_dir,
                provider="bitbucket",
                run_id="test-run",
                force_lock=False,
            )
            self.assertTrue(lock_info["replaced_stale"])
            release_run_lock(lock_info["path"])


if __name__ == "__main__":
    unittest.main()