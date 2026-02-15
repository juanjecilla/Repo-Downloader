import json
import os
import tempfile
import unittest
from unittest.mock import patch

from datetime import datetime, timezone

from utils.repo_utils import (
    acquire_run_lock,
    build_backup_paths,
    build_checkpoint_path,
    build_run_lock_path,
    build_snapshot_path,
    collect_snapshot_paths,
    create_snapshot_archive,
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
    snapshot_timestamp,
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

    def test_snapshot_timestamp_returns_iso_format(self):
        timestamp = snapshot_timestamp()
        self.assertRegex(timestamp, r"^\d{8}T\d{6}Z$")

    def test_snapshot_timestamp_accepts_custom_datetime(self):
        dt = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        timestamp = snapshot_timestamp(dt)
        self.assertEqual("20240115T123045Z", timestamp)

    def test_build_snapshot_path_zip_format(self):
        path = build_snapshot_path(
            snapshot_dir="./snapshots",
            provider="bitbucket",
            workspace="acme",
            repository_name="example",
            snapshot_format="zip",
            timestamp="20240101T000000Z",
        )
        self.assertTrue(path.endswith("bitbucket/acme/example-20240101T000000Z.zip"))

    def test_build_snapshot_path_tar_gz_format(self):
        path = build_snapshot_path(
            snapshot_dir="./snapshots",
            provider="github",
            workspace="team",
            repository_name="project",
            snapshot_format="tar.gz",
            timestamp="20240201T120000Z",
        )
        self.assertTrue(path.endswith("github/team/project-20240201T120000Z.tar.gz"))

    def test_build_snapshot_path_raises_for_unsupported_format(self):
        with self.assertRaises(ValueError) as context:
            build_snapshot_path(
                snapshot_dir="./snapshots",
                provider="bitbucket",
                workspace="acme",
                repository_name="example",
                snapshot_format="rar",
            )
        self.assertIn("Unsupported snapshot format", str(context.exception))

    def test_create_snapshot_archive_zip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "repo.git")
            os.makedirs(source_path, exist_ok=True)
            with open(os.path.join(source_path, "config"), "w", encoding="utf-8") as config_file:
                config_file.write("[core]\n")

            snapshot_dir = os.path.join(tmp_dir, "snapshots")
            snapshot_path = os.path.join(snapshot_dir, "bitbucket", "acme", "repo-20240101T000000Z.zip")

            created_path = create_snapshot_archive(source_path, snapshot_path, "zip")

            self.assertTrue(os.path.exists(created_path))
            self.assertTrue(created_path.endswith(".zip"))

    def test_create_snapshot_archive_tar_gz(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "repo.git")
            os.makedirs(source_path, exist_ok=True)
            with open(os.path.join(source_path, "config"), "w", encoding="utf-8") as config_file:
                config_file.write("[core]\n")

            snapshot_dir = os.path.join(tmp_dir, "snapshots")
            snapshot_path = os.path.join(snapshot_dir, "github", "team", "repo-20240101T000000Z.tar.gz")

            created_path = create_snapshot_archive(source_path, snapshot_path, "tar.gz")

            self.assertTrue(os.path.exists(created_path))
            self.assertTrue(created_path.endswith(".tar.gz"))

    def test_create_snapshot_archive_raises_for_unsupported_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "repo.git")
            os.makedirs(source_path, exist_ok=True)
            snapshot_path = os.path.join(tmp_dir, "repo-20240101T000000Z.rar")

            with self.assertRaises(ValueError) as context:
                create_snapshot_archive(source_path, snapshot_path, "rar")

            self.assertIn("Unsupported snapshot format", str(context.exception))

    def test_build_checkpoint_path(self):
        path = build_checkpoint_path("./backups", "bitbucket")
        self.assertTrue(path.endswith("bitbucket/.repo-downloader-checkpoint.json"))

    def test_save_and_load_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_path = build_checkpoint_path(tmp_dir, "bitbucket")
            payload = {
                "signature": {"provider": "bitbucket", "mode": "mirror"},
                "completed": ["acme/one", "acme/two"],
            }

            save_checkpoint(checkpoint_path, payload)
            loaded = load_checkpoint(checkpoint_path)

            self.assertEqual(payload, loaded)

    def test_load_checkpoint_returns_empty_dict_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_path = os.path.join(tmp_dir, "missing.json")
            loaded = load_checkpoint(checkpoint_path)
            self.assertEqual({}, loaded)

    def test_load_checkpoint_returns_empty_dict_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_path = os.path.join(tmp_dir, "invalid.json")
            with open(checkpoint_path, "w", encoding="utf-8") as checkpoint_file:
                checkpoint_file.write("invalid json content")

            loaded = load_checkpoint(checkpoint_path)
            self.assertEqual({}, loaded)

    def test_remove_checkpoint_deletes_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_path = os.path.join(tmp_dir, "checkpoint.json")
            with open(checkpoint_path, "w", encoding="utf-8") as checkpoint_file:
                checkpoint_file.write("{}")

            remove_checkpoint(checkpoint_path)

            self.assertFalse(os.path.exists(checkpoint_path))

    def test_remove_checkpoint_does_not_raise_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_path = os.path.join(tmp_dir, "missing.json")
            remove_checkpoint(checkpoint_path)

    def test_parse_repository_entry_flat_structure(self):
        parsed = parse_repository_entry({"full_name": "acme/repo"})
        self.assertEqual("acme", parsed["workspace"])
        self.assertEqual("repo", parsed["name"])
        self.assertEqual("acme/repo", parsed["full_name"])

    def test_parse_repository_entry_missing_full_name_raises(self):
        with self.assertRaises(KeyError):
            parse_repository_entry({"repository": {"name": "repo"}})

    def test_extract_workspace_and_name_with_slash(self):
        workspace, name = extract_workspace_and_name("workspace/repository-name")
        self.assertEqual("workspace", workspace)
        self.assertEqual("repository-name", name)

    def test_extract_workspace_and_name_empty_workspace_raises(self):
        with self.assertRaises(ValueError):
            extract_workspace_and_name("/repository")

    def test_extract_workspace_and_name_empty_name_raises(self):
        with self.assertRaises(ValueError):
            extract_workspace_and_name("workspace/")

    def test_filter_repositories_by_workspace_no_filter_returns_all(self):
        repositories = [
            {"repository": {"full_name": "acme/one"}},
            {"repository": {"full_name": "other/two"}},
        ]
        filtered = filter_repositories_by_workspace(repositories, None)
        self.assertEqual(2, len(filtered))

    def test_is_archived_repository_checks_is_archived_field(self):
        summary = {"full_name": "acme/repo", "is_archived": True}
        self.assertTrue(is_archived_repository(summary))

    def test_is_archived_repository_checks_archived_field(self):
        summary = {"full_name": "acme/repo", "archived": True}
        self.assertTrue(is_archived_repository(summary))

    def test_is_archived_repository_checks_nested_repository(self):
        summary = {"repository": {"full_name": "acme/repo", "is_archived": True}}
        self.assertTrue(is_archived_repository(summary))

    def test_is_archived_repository_returns_false_when_not_archived(self):
        summary = {"full_name": "acme/repo", "is_archived": False, "archived": False}
        extended = {"full_name": "acme/repo", "is_archived": False}
        self.assertFalse(is_archived_repository(summary, extended))


if __name__ == "__main__":
    unittest.main()