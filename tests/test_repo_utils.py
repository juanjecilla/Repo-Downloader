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


class TestRepoUtilsEdgeCases(unittest.TestCase):
    def test_extract_workspace_and_name_with_multiple_slashes(self):
        workspace, name = extract_workspace_and_name("acme/subgroup/repo")
        self.assertEqual("acme", workspace)
        self.assertEqual("subgroup/repo", name)

    def test_extract_workspace_and_name_empty_workspace(self):
        with self.assertRaises(ValueError) as context:
            extract_workspace_and_name("/repo")
        self.assertIn("Invalid repository full name", str(context.exception))

    def test_extract_workspace_and_name_empty_name(self):
        with self.assertRaises(ValueError) as context:
            extract_workspace_and_name("acme/")
        self.assertIn("Invalid repository full name", str(context.exception))

    def test_extract_workspace_and_name_no_slash(self):
        with self.assertRaises(ValueError) as context:
            extract_workspace_and_name("invalid-name")
        self.assertIn("Invalid repository full name", str(context.exception))

    def test_parse_repository_entry_direct_format(self):
        parsed = parse_repository_entry({"full_name": "acme/repo"})
        self.assertEqual("acme", parsed["workspace"])
        self.assertEqual("repo", parsed["name"])

    def test_parse_repository_entry_missing_full_name(self):
        with self.assertRaises(KeyError) as context:
            parse_repository_entry({"repository": {"name": "repo"}})
        self.assertIn("full_name", str(context.exception))

    def test_filter_repositories_by_workspace_none_workspace(self):
        repositories = [
            {"repository": {"full_name": "acme/one"}},
            {"repository": {"full_name": "other/two"}},
        ]
        result = filter_repositories_by_workspace(repositories, None)
        self.assertEqual(2, len(result))

    def test_filter_repositories_by_workspace_empty_string(self):
        repositories = [{"repository": {"full_name": "acme/one"}}]
        result = filter_repositories_by_workspace(repositories, "")
        self.assertEqual(1, len(result))

    def test_filter_repositories_by_workspace_case_insensitive(self):
        repositories = [
            {"repository": {"full_name": "AcMe/repo"}},
            {"repository": {"full_name": "other/repo"}},
        ]
        result = filter_repositories_by_workspace(repositories, "acme")
        self.assertEqual(1, len(result))
        self.assertEqual("AcMe/repo", result[0]["repository"]["full_name"])

    def test_filter_repositories_by_workspace_direct_format(self):
        repositories = [{"full_name": "acme/one"}, {"full_name": "other/two"}]
        result = filter_repositories_by_workspace(repositories, "acme")
        self.assertEqual(1, len(result))

    def test_is_archived_repository_nested_repository_field(self):
        entry = {"repository": {"is_archived": True}}
        self.assertTrue(is_archived_repository(entry))

    def test_is_archived_repository_extended_has_archived(self):
        summary = {"full_name": "acme/repo"}
        extended = {"archived": True}
        self.assertTrue(is_archived_repository(summary, extended))

    def test_is_archived_repository_both_false(self):
        summary = {"is_archived": False}
        extended = {"archived": False}
        self.assertFalse(is_archived_repository(summary, extended))

    def test_is_archived_repository_no_archive_fields(self):
        summary = {"full_name": "acme/repo"}
        extended = {"full_name": "acme/repo"}
        self.assertFalse(is_archived_repository(summary, extended))

    def test_build_backup_paths_expands_tilde(self):
        paths = build_backup_paths("~/backups", "bitbucket", "acme", "repo")
        self.assertNotIn("~", paths["base_dir"])
        self.assertNotIn("~", paths["mirror_path"])
        self.assertNotIn("~", paths["working_path"])

    def test_normalize_repo_patterns_none_input(self):
        result = normalize_repo_patterns(None)
        self.assertEqual([], result)

    def test_normalize_repo_patterns_empty_list(self):
        result = normalize_repo_patterns([])
        self.assertEqual([], result)

    def test_normalize_repo_patterns_removes_empty_strings(self):
        result = normalize_repo_patterns(["", "acme/*", "  ", "other/*"])
        self.assertEqual(["acme/*", "other/*"], result)

    def test_normalize_repo_patterns_handles_mixed_case(self):
        result = normalize_repo_patterns(["ACME/*", "Other/Repo"])
        self.assertEqual(["acme/*", "other/repo"], result)

    def test_repository_matches_filters_both_filters_empty(self):
        matches, reason, detail = repository_matches_filters("acme/repo", [], [])
        self.assertTrue(matches)
        self.assertIsNone(reason)

    def test_repository_matches_filters_none_filters(self):
        matches, reason, detail = repository_matches_filters("acme/repo", None, None)
        self.assertTrue(matches)
        self.assertIsNone(reason)

    def test_repository_matches_filters_wildcard_include(self):
        matches, reason, detail = repository_matches_filters("acme/repo", ["*"], [])
        self.assertTrue(matches)

    def test_repository_matches_filters_wildcard_exclude(self):
        matches, reason, detail = repository_matches_filters("acme/repo", [], ["*"])
        self.assertFalse(matches)
        self.assertEqual("exclude_match", reason)

    def test_build_run_lock_path_creates_correct_name(self):
        path = build_run_lock_path("/tmp/backups", "bitbucket")
        self.assertTrue(path.endswith(".repo-downloader-bitbucket.lock"))
        self.assertIn("/tmp/backups", path)

    def test_is_process_running_negative_pid(self):
        self.assertFalse(is_process_running(-1))

    def test_is_process_running_zero_pid(self):
        self.assertFalse(is_process_running(0))

    def test_is_process_running_none_pid(self):
        self.assertFalse(is_process_running(None))

    def test_is_process_running_non_integer(self):
        self.assertFalse(is_process_running("not-a-number"))

    def test_is_process_running_current_process(self):
        self.assertTrue(is_process_running(os.getpid()))

    def test_is_process_running_nonexistent_pid(self):
        self.assertFalse(is_process_running(999999))

    def test_acquire_run_lock_creates_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            nested_output = os.path.join(tmp_dir, "nested", "output")
            lock_info = acquire_run_lock(
                output_dir=nested_output,
                provider="bitbucket",
                run_id="test",
                force_lock=False,
            )
            self.assertTrue(os.path.exists(nested_output))
            release_run_lock(lock_info["path"])

    def test_acquire_run_lock_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_info = acquire_run_lock(
                output_dir=tmp_dir,
                provider="bitbucket",
                run_id="test-run",
                force_lock=False,
            )

            with open(lock_info["path"], "r", encoding="utf-8") as lock_file:
                payload = json.load(lock_file)

            self.assertEqual(os.getpid(), payload["pid"])
            self.assertEqual("bitbucket", payload["provider"])
            self.assertEqual("test-run", payload["run_id"])
            self.assertIn("created_at", payload)
            release_run_lock(lock_info["path"])

    def test_release_run_lock_handles_nonexistent_file(self):
        try:
            release_run_lock("/nonexistent/path/to.lock")
        except Exception as exc:
            self.fail(f"release_run_lock should handle missing file gracefully: {exc}")

    def test_release_run_lock_raises_on_permission_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = os.path.join(tmp_dir, "test.lock")
            with open(lock_path, "w", encoding="utf-8") as lock_file:
                lock_file.write("{}")

            with patch("os.remove", side_effect=PermissionError("Access denied")):
                with self.assertRaises(RunLockError) as context:
                    release_run_lock(lock_path)

                self.assertIn("Unable to remove", str(context.exception))


if __name__ == "__main__":
    unittest.main()