import json
import os
import tempfile
import unittest
from unittest.mock import patch

from utils.repo_utils import (
    acquire_run_lock,
    build_backup_paths,
    build_run_lock_path,
    build_snapshot_path,
    create_snapshot_archive,
    extract_workspace_and_name,
    filter_repositories_by_workspace,
    is_archived_repository,
    normalize_repo_patterns,
    parse_repository_entry,
    release_run_lock,
    repository_matches_filters,
    snapshot_timestamp,
    utc_now_iso,
)
from utils.errors import RunLockError
from datetime import datetime, timezone


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


class TestSnapshotUtils(unittest.TestCase):
    def test_snapshot_timestamp_returns_formatted_string(self):
        dt = datetime(2025, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = snapshot_timestamp(dt)
        self.assertEqual("20250115T143045Z", result)

    def test_snapshot_timestamp_uses_current_time_when_none(self):
        result = snapshot_timestamp()
        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith("Z"))
        self.assertIn("T", result)

    def test_build_snapshot_path_zip_format(self):
        path = build_snapshot_path(
            snapshot_dir="./snapshots",
            provider="github",
            workspace="acme",
            repository_name="repo",
            snapshot_format="zip",
            timestamp="20250115T120000Z",
        )
        self.assertTrue(path.endswith("/github/acme/repo-20250115T120000Z.zip"))

    def test_build_snapshot_path_tar_gz_format(self):
        path = build_snapshot_path(
            snapshot_dir="./snapshots",
            provider="gitlab",
            workspace="acme",
            repository_name="repo",
            snapshot_format="tar.gz",
            timestamp="20250115T120000Z",
        )
        self.assertTrue(path.endswith("/gitlab/acme/repo-20250115T120000Z.tar.gz"))

    def test_build_snapshot_path_expands_user_directory(self):
        path = build_snapshot_path(
            snapshot_dir="~/snapshots",
            provider="github",
            workspace="acme",
            repository_name="repo",
            snapshot_format="zip",
            timestamp="20250115T120000Z",
        )
        self.assertNotIn("~", path)
        self.assertTrue(path.endswith(".zip"))

    def test_build_snapshot_path_generates_timestamp_when_not_provided(self):
        path1 = build_snapshot_path(
            snapshot_dir="./snapshots",
            provider="github",
            workspace="acme",
            repository_name="repo",
            snapshot_format="zip",
        )
        path2 = build_snapshot_path(
            snapshot_dir="./snapshots",
            provider="github",
            workspace="acme",
            repository_name="repo",
            snapshot_format="zip",
        )
        # Both paths should exist and end with .zip
        self.assertTrue(path1.endswith(".zip"))
        self.assertTrue(path2.endswith(".zip"))

    def test_build_snapshot_path_raises_on_invalid_format(self):
        with self.assertRaises(ValueError) as ctx:
            build_snapshot_path(
                snapshot_dir="./snapshots",
                provider="github",
                workspace="acme",
                repository_name="repo",
                snapshot_format="rar",
            )
        self.assertIn("Unsupported snapshot format", str(ctx.exception))

    def test_create_snapshot_archive_zip_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create source directory with content
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)
            test_file = os.path.join(source_path, "test.txt")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("test content")

            # Create snapshot
            snapshot_path = os.path.join(tmp_dir, "snapshots", "test.zip")
            result_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            self.assertEqual(snapshot_path, result_path)
            self.assertTrue(os.path.exists(result_path))
            self.assertTrue(result_path.endswith(".zip"))

    def test_create_snapshot_archive_tar_gz_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create source directory with content
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)
            test_file = os.path.join(source_path, "test.txt")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("test content")

            # Create snapshot
            snapshot_path = os.path.join(tmp_dir, "snapshots", "test.tar.gz")
            result_path = create_snapshot_archive(source_path, snapshot_path, "tar.gz")

            self.assertEqual(snapshot_path, result_path)
            self.assertTrue(os.path.exists(result_path))
            self.assertTrue(result_path.endswith(".tar.gz"))

    def test_create_snapshot_archive_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create source directory
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)

            # Snapshot path with non-existent parent directory
            snapshot_path = os.path.join(tmp_dir, "nested", "dir", "snapshot.zip")
            self.assertFalse(os.path.exists(os.path.dirname(snapshot_path)))

            result_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            self.assertTrue(os.path.exists(result_path))
            self.assertTrue(os.path.exists(os.path.dirname(snapshot_path)))

    def test_create_snapshot_archive_raises_on_invalid_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)
            snapshot_path = os.path.join(tmp_dir, "snapshot.unknown")

            with self.assertRaises(ValueError) as ctx:
                create_snapshot_archive(source_path, snapshot_path, "unknown")

            self.assertIn("Unsupported snapshot format", str(ctx.exception))

    def test_utc_now_iso_returns_iso_format(self):
        result = utc_now_iso()
        self.assertIsInstance(result, str)
        self.assertIn("T", result)
        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(result)
        self.assertIsInstance(parsed, datetime)


class TestRepoUtilsEdgeCases(unittest.TestCase):
    def test_extract_workspace_and_name_with_multiple_slashes(self):
        # Only the first slash should split workspace and name
        workspace, name = extract_workspace_and_name("acme/nested/repo-name")
        self.assertEqual("acme", workspace)
        self.assertEqual("nested/repo-name", name)

    def test_extract_workspace_and_name_empty_parts_raises(self):
        with self.assertRaises(ValueError):
            extract_workspace_and_name("/repo")
        with self.assertRaises(ValueError):
            extract_workspace_and_name("workspace/")
        with self.assertRaises(ValueError):
            extract_workspace_and_name("/")

    def test_parse_repository_entry_missing_full_name_raises(self):
        with self.assertRaises(KeyError):
            parse_repository_entry({"repository": {"name": "repo"}})

    def test_parse_repository_entry_direct_format(self):
        # When repository is not nested under "repository" key
        parsed = parse_repository_entry({"full_name": "acme/repo"})
        self.assertEqual("acme", parsed["workspace"])
        self.assertEqual("repo", parsed["name"])

    def test_filter_repositories_by_workspace_case_insensitive(self):
        repositories = [
            {"repository": {"full_name": "ACME/one"}},
            {"repository": {"full_name": "other/two"}},
        ]
        filtered = filter_repositories_by_workspace(repositories, "acme")
        self.assertEqual(1, len(filtered))

    def test_filter_repositories_by_workspace_none_returns_all(self):
        repositories = [
            {"repository": {"full_name": "acme/one"}},
            {"repository": {"full_name": "other/two"}},
        ]
        filtered = filter_repositories_by_workspace(repositories, None)
        self.assertEqual(2, len(filtered))

    def test_is_archived_repository_with_nested_repository_key(self):
        # When the main entry has repository.is_archived
        entry = {"repository": {"is_archived": True}}
        self.assertTrue(is_archived_repository(entry))

    def test_is_archived_repository_all_false_returns_false(self):
        summary = {"is_archived": False, "archived": False}
        extended = {"is_archived": False, "archived": False}
        self.assertFalse(is_archived_repository(summary, extended))

    def test_is_archived_repository_no_extended_uses_summary_only(self):
        summary = {"archived": True}
        self.assertTrue(is_archived_repository(summary, None))

    def test_normalize_repo_patterns_empty_input(self):
        result = normalize_repo_patterns([])
        self.assertEqual([], result)

    def test_normalize_repo_patterns_none_input(self):
        result = normalize_repo_patterns(None)
        self.assertEqual([], result)

    def test_normalize_repo_patterns_strips_whitespace(self):
        result = normalize_repo_patterns(["  acme/*  ", " other/* "])
        self.assertEqual(["acme/*", "other/*"], result)

    def test_normalize_repo_patterns_filters_empty_strings(self):
        result = normalize_repo_patterns(["acme/*", "", "  ", "other/*"])
        self.assertEqual(["acme/*", "other/*"], result)

    def test_repository_matches_filters_empty_patterns_matches_all(self):
        matches, _, _ = repository_matches_filters("any/repo", [], [])
        self.assertTrue(matches)

    def test_build_backup_paths_expands_tilde(self):
        paths = build_backup_paths("~/backups", "github", "acme", "repo")
        self.assertNotIn("~", paths["base_dir"])
        self.assertNotIn("~", paths["mirror_path"])
        self.assertNotIn("~", paths["working_path"])


if __name__ == "__main__":
    unittest.main()