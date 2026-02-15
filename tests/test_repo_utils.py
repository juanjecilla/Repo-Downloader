import json
import os
import tempfile
import unittest
from unittest.mock import patch

from utils.repo_utils import (
    acquire_run_lock,
    build_backup_paths,
    build_run_lock_path,
    collect_snapshot_paths,
    delete_artifact_path,
    extract_workspace_and_name,
    filter_repositories_by_workspace,
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
from utils.errors import RunLockError


class TestRepoUtils(unittest.TestCase):  # pylint: disable=too-many-public-methods
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
                json.dump(
                    {"pid": 999999, "provider": "bitbucket", "run_id": "old"},
                    lock_file,
                )

            with patch("utils.repo_utils.is_process_running", return_value=False):
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

    def test_collect_snapshot_paths_returns_matching_archives(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_dir = os.path.join(tmp_dir, "bitbucket", "acme")
            os.makedirs(workspace_dir, exist_ok=True)
            expected_zip = os.path.join(workspace_dir, "example-20240101T000000Z.zip")
            expected_tar = os.path.join(workspace_dir, "example-20240102T000000Z.tar.gz")
            with open(expected_zip, "w", encoding="utf-8") as file_zip:
                file_zip.write("zip")
            with open(expected_tar, "w", encoding="utf-8") as file_tar:
                file_tar.write("tar")
            with open(
                os.path.join(workspace_dir, "other-20240102T000000Z.zip"),
                "w",
                encoding="utf-8",
            ) as other_file:
                other_file.write("other")

            collected = collect_snapshot_paths(tmp_dir, "bitbucket", "acme", "example")

            self.assertEqual(2, len(collected))
            self.assertIn(expected_zip, collected)
            self.assertIn(expected_tar, collected)

    def test_plan_retention_deletions_by_days_and_count(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = os.path.join(tmp_dir, "first.txt")
            second = os.path.join(tmp_dir, "second.txt")
            third = os.path.join(tmp_dir, "third.txt")
            for path in (first, second, third):
                with open(path, "w", encoding="utf-8") as file_handle:
                    file_handle.write(path)

            os.utime(first, (100, 100))
            os.utime(second, (200, 200))
            os.utime(third, (300, 300))

            deletions = plan_retention_deletions(
                [first, second, third],
                retain_days=2,
                retain_count=2,
                now_timestamp=300 + (2 * 86400),
            )

            self.assertEqual([second, first], deletions)

    def test_delete_artifact_path_removes_file_and_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "snapshot.zip")
            dir_path = os.path.join(tmp_dir, "working-copy")
            os.makedirs(dir_path, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as file_handle:
                file_handle.write("snapshot")
            with open(os.path.join(dir_path, "README.md"), "w", encoding="utf-8") as file_handle:
                file_handle.write("working")

            delete_artifact_path(file_path)
            delete_artifact_path(dir_path)

            self.assertFalse(os.path.exists(file_path))
            self.assertFalse(os.path.exists(dir_path))

    def test_snapshot_timestamp_generates_iso_format(self):
        from datetime import datetime, timezone
        from utils.repo_utils import snapshot_timestamp

        now = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        timestamp = snapshot_timestamp(now)
        self.assertEqual("20240115T103045Z", timestamp)

    def test_build_snapshot_path_uses_custom_timestamp(self):
        from utils.repo_utils import build_snapshot_path

        path = build_snapshot_path(
            snapshot_dir="./snapshots",
            provider="bitbucket",
            workspace="acme",
            repository_name="service",
            snapshot_format="zip",
            timestamp="20240101T120000Z",
        )
        self.assertTrue(path.endswith("/acme/service-20240101T120000Z.zip"))

    def test_build_snapshot_path_raises_for_unsupported_format(self):
        from utils.repo_utils import build_snapshot_path

        with self.assertRaises(ValueError) as ctx:
            build_snapshot_path(
                snapshot_dir="./snapshots",
                provider="bitbucket",
                workspace="acme",
                repository_name="service",
                snapshot_format="rar",
            )
        self.assertIn("Unsupported snapshot format", str(ctx.exception))

    def test_create_snapshot_archive_raises_for_unsupported_format(self):
        from utils.repo_utils import create_snapshot_archive

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "repo.git")
            os.makedirs(source_path)
            snapshot_path = os.path.join(tmp_dir, "snapshot.rar")

            with self.assertRaises(ValueError):
                create_snapshot_archive(source_path, snapshot_path, "rar")

    def test_plan_retention_deletions_returns_empty_when_no_policies(self):
        paths = ["/tmp/file1.zip", "/tmp/file2.zip"]
        deletions = plan_retention_deletions(paths, retain_days=None, retain_count=None)
        self.assertEqual([], deletions)

    def test_plan_retention_deletions_handles_missing_files(self):
        deletions = plan_retention_deletions(
            ["/nonexistent/file.zip"],
            retain_days=1,
            retain_count=1,
        )
        self.assertEqual([], deletions)

    def test_load_checkpoint_returns_empty_dict_for_missing_file(self):
        checkpoint = load_checkpoint("/nonexistent/checkpoint.json")
        self.assertEqual({}, checkpoint)

    def test_load_checkpoint_returns_empty_dict_for_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_path = os.path.join(tmp_dir, "checkpoint.json")
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                f.write("not valid json")

            checkpoint = load_checkpoint(checkpoint_path)
            self.assertEqual({}, checkpoint)

    def test_save_checkpoint_creates_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_path = os.path.join(tmp_dir, "nested", "checkpoint.json")
            payload = {"signature": {"provider": "bitbucket"}, "completed": []}
            save_checkpoint(checkpoint_path, payload)

            self.assertTrue(os.path.isfile(checkpoint_path))
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(payload, loaded)

    def test_remove_checkpoint_does_not_raise_if_file_missing(self):
        remove_checkpoint("/nonexistent/checkpoint.json")

    def test_is_process_running_returns_false_for_invalid_pid(self):
        from utils.repo_utils import is_process_running

        self.assertFalse(is_process_running(None))
        self.assertFalse(is_process_running(0))
        self.assertFalse(is_process_running(-1))

    def test_is_process_running_returns_true_for_current_process(self):
        from utils.repo_utils import is_process_running

        self.assertTrue(is_process_running(os.getpid()))

    def test_is_process_running_returns_false_for_nonexistent_pid(self):
        from utils.repo_utils import is_process_running

        self.assertFalse(is_process_running(999999))

    def test_build_run_lock_path_formats_correctly(self):
        lock_path = build_run_lock_path("./output", "bitbucket")
        self.assertTrue(lock_path.endswith(".repo-downloader-bitbucket.lock"))

    def test_repository_matches_filters_handles_uppercase_input(self):
        matches, reason, detail = repository_matches_filters(
            full_name="ACME/REPO",
            include_patterns=["acme/*"],
            exclude_patterns=[],
        )
        self.assertTrue(matches)

    def test_repository_matches_filters_supports_exact_match(self):
        matches, reason, detail = repository_matches_filters(
            full_name="acme/specific-repo",
            include_patterns=["acme/specific-repo"],
            exclude_patterns=[],
        )
        self.assertTrue(matches)

    def test_filter_repositories_by_workspace_case_insensitive(self):
        repositories = [
            {"repository": {"full_name": "Acme/one"}},
            {"repository": {"full_name": "acme/two"}},
            {"repository": {"full_name": "Other/three"}},
        ]
        filtered = filter_repositories_by_workspace(repositories, "ACME")
        self.assertEqual(2, len(filtered))

    def test_is_archived_repository_checks_nested_repository_field(self):
        entry = {
            "repository": {
                "full_name": "acme/repo",
                "archived": True,
            }
        }
        self.assertTrue(is_archived_repository(entry))

    def test_parse_repository_entry_raises_key_error_for_missing_full_name(self):
        with self.assertRaises(KeyError):
            parse_repository_entry({"repository": {}})

    def test_extract_workspace_and_name_raises_for_missing_slash(self):
        with self.assertRaises(ValueError):
            extract_workspace_and_name("invalid")

    def test_extract_workspace_and_name_raises_for_empty_parts(self):
        with self.assertRaises(ValueError):
            extract_workspace_and_name("/repo")
        with self.assertRaises(ValueError):
            extract_workspace_and_name("workspace/")


if __name__ == "__main__":
    unittest.main()