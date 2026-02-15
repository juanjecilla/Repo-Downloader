import json
import os
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
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


class TestSnapshotTimestamp(unittest.TestCase):
    def test_snapshot_timestamp_returns_string(self):
        timestamp = snapshot_timestamp()
        self.assertIsInstance(timestamp, str)

    def test_snapshot_timestamp_format(self):
        timestamp = snapshot_timestamp()
        self.assertRegex(timestamp, r"^\d{8}T\d{6}Z$")

    def test_snapshot_timestamp_accepts_datetime_parameter(self):
        fixed_time = datetime(2024, 3, 15, 10, 30, 45, tzinfo=timezone.utc)
        timestamp = snapshot_timestamp(now=fixed_time)
        self.assertEqual("20240315T103045Z", timestamp)

    def test_snapshot_timestamp_uses_utc(self):
        timestamp = snapshot_timestamp()
        self.assertTrue(timestamp.endswith("Z"))

    def test_snapshot_timestamp_year_component(self):
        fixed_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        timestamp = snapshot_timestamp(now=fixed_time)
        self.assertTrue(timestamp.startswith("2025"))

    def test_snapshot_timestamp_pads_month_and_day(self):
        fixed_time = datetime(2024, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
        timestamp = snapshot_timestamp(now=fixed_time)
        self.assertTrue(timestamp.startswith("20240105"))

    def test_snapshot_timestamp_includes_time_components(self):
        fixed_time = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        timestamp = snapshot_timestamp(now=fixed_time)
        self.assertEqual("20241231T235959Z", timestamp)


class TestBuildSnapshotPath(unittest.TestCase):
    def test_build_snapshot_path_zip_format(self):
        path = build_snapshot_path(
            snapshot_dir="/snapshots",
            provider="bitbucket",
            workspace="acme",
            repository_name="repo",
            snapshot_format="zip",
            timestamp="20240315T120000Z",
        )
        self.assertEqual("/snapshots/bitbucket/acme/repo-20240315T120000Z.zip", path)

    def test_build_snapshot_path_tar_gz_format(self):
        path = build_snapshot_path(
            snapshot_dir="/snapshots",
            provider="github",
            workspace="acme",
            repository_name="service",
            snapshot_format="tar.gz",
            timestamp="20240315T120000Z",
        )
        self.assertEqual("/snapshots/github/acme/service-20240315T120000Z.tar.gz", path)

    def test_build_snapshot_path_generates_timestamp_if_not_provided(self):
        path = build_snapshot_path(
            snapshot_dir="/snapshots",
            provider="bitbucket",
            workspace="acme",
            repository_name="repo",
            snapshot_format="zip",
        )
        self.assertTrue(path.startswith("/snapshots/bitbucket/acme/repo-"))
        self.assertTrue(path.endswith(".zip"))

    def test_build_snapshot_path_expands_tilde_in_directory(self):
        with patch("os.path.expanduser", return_value="/home/user/snapshots"):
            path = build_snapshot_path(
                snapshot_dir="~/snapshots",
                provider="bitbucket",
                workspace="acme",
                repository_name="repo",
                snapshot_format="zip",
                timestamp="20240315T120000Z",
            )
            self.assertTrue(path.startswith("/home/user/snapshots"))

    def test_build_snapshot_path_includes_provider_workspace_repo_in_path(self):
        path = build_snapshot_path(
            snapshot_dir="/snapshots",
            provider="gitlab",
            workspace="team",
            repository_name="project",
            snapshot_format="zip",
            timestamp="20240315T120000Z",
        )
        self.assertIn("/gitlab/", path)
        self.assertIn("/team/", path)
        self.assertIn("project-", path)

    def test_build_snapshot_path_raises_value_error_for_unsupported_format(self):
        with self.assertRaises(ValueError) as context:
            build_snapshot_path(
                snapshot_dir="/snapshots",
                provider="bitbucket",
                workspace="acme",
                repository_name="repo",
                snapshot_format="rar",
                timestamp="20240315T120000Z",
            )
        self.assertIn("Unsupported snapshot format", str(context.exception))
        self.assertIn("rar", str(context.exception))


class TestCreateSnapshotArchive(unittest.TestCase):
    def test_create_snapshot_archive_creates_zip_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)
            with open(os.path.join(source_path, "test.txt"), "w", encoding="utf-8") as f:
                f.write("test content")

            snapshot_path = os.path.join(tmp_dir, "snapshot", "repo.zip")
            result_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            self.assertTrue(os.path.exists(result_path))
            self.assertTrue(result_path.endswith(".zip"))

    def test_create_snapshot_archive_creates_tar_gz_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)
            with open(os.path.join(source_path, "test.txt"), "w", encoding="utf-8") as f:
                f.write("test content")

            snapshot_path = os.path.join(tmp_dir, "snapshot", "repo.tar.gz")
            result_path = create_snapshot_archive(source_path, snapshot_path, "tar.gz")

            self.assertTrue(os.path.exists(result_path))
            self.assertTrue(result_path.endswith(".tar.gz"))

    def test_create_snapshot_archive_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)
            with open(os.path.join(source_path, "test.txt"), "w", encoding="utf-8") as f:
                f.write("test content")

            snapshot_path = os.path.join(tmp_dir, "nested", "deep", "snapshot.zip")
            create_snapshot_archive(source_path, snapshot_path, "zip")

            self.assertTrue(os.path.exists(os.path.dirname(snapshot_path)))

    def test_create_snapshot_archive_zip_contains_source_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)
            with open(os.path.join(source_path, "test.txt"), "w", encoding="utf-8") as f:
                f.write("test content")

            snapshot_path = os.path.join(tmp_dir, "snapshot.zip")
            result_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            with zipfile.ZipFile(result_path, "r") as zf:
                names = zf.namelist()
                self.assertIn("source.git/test.txt", names)

    def test_create_snapshot_archive_tar_gz_contains_source_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)
            with open(os.path.join(source_path, "test.txt"), "w", encoding="utf-8") as f:
                f.write("test content")

            snapshot_path = os.path.join(tmp_dir, "snapshot.tar.gz")
            result_path = create_snapshot_archive(source_path, snapshot_path, "tar.gz")

            with tarfile.open(result_path, "r:gz") as tf:
                names = tf.getnames()
                self.assertIn("source.git/test.txt", names)

    def test_create_snapshot_archive_preserves_directory_structure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            nested_dir = os.path.join(source_path, "nested", "directory")
            os.makedirs(nested_dir)
            with open(os.path.join(nested_dir, "file.txt"), "w", encoding="utf-8") as f:
                f.write("nested content")

            snapshot_path = os.path.join(tmp_dir, "snapshot.zip")
            result_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            with zipfile.ZipFile(result_path, "r") as zf:
                names = zf.namelist()
                self.assertIn("source.git/nested/directory/file.txt", names)

    def test_create_snapshot_archive_returns_created_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)

            snapshot_path = os.path.join(tmp_dir, "snapshot.zip")
            result_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            self.assertEqual(snapshot_path, result_path)

    def test_create_snapshot_archive_raises_value_error_for_unsupported_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "source.git")
            os.makedirs(source_path)

            snapshot_path = os.path.join(tmp_dir, "snapshot.rar")
            with self.assertRaises(ValueError) as context:
                create_snapshot_archive(source_path, snapshot_path, "rar")

            self.assertIn("Unsupported snapshot format", str(context.exception))
            self.assertIn("rar", str(context.exception))

    def test_create_snapshot_archive_handles_empty_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "empty.git")
            os.makedirs(source_path)

            snapshot_path = os.path.join(tmp_dir, "snapshot.zip")
            result_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            self.assertTrue(os.path.exists(result_path))
            with zipfile.ZipFile(result_path, "r") as zf:
                names = zf.namelist()
                self.assertTrue(any("empty.git" in name for name in names))

    def test_create_snapshot_archive_uses_source_parent_as_root_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent_dir = os.path.join(tmp_dir, "parent")
            source_path = os.path.join(parent_dir, "repo.git")
            os.makedirs(source_path)
            with open(os.path.join(source_path, "file.txt"), "w", encoding="utf-8") as f:
                f.write("content")

            snapshot_path = os.path.join(tmp_dir, "snapshot.zip")
            result_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            with zipfile.ZipFile(result_path, "r") as zf:
                names = zf.namelist()
                self.assertTrue(any(name.startswith("repo.git/") for name in names))


if __name__ == "__main__":
    unittest.main()