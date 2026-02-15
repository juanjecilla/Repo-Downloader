import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import downloader
from utils.errors import (
    AuthenticationError,
    ProviderConfigurationError,
    RemoteAPIError,
    RepositorySyncError,
    RunLockError,
)
from utils.log_utils import REDACTED_VALUE, RunLogger


class _FakeProvider:
    def __init__(self, repositories=None, branches=None):
        if repositories is None:
            repositories = [{"repository": {"full_name": "acme/example"}}]
        self._repositories = repositories
        self._branches = branches or [{"name": "main"}, {"name": "dev"}]

    def list_repositories(self, workspace=None, role="member"):
        _ = workspace
        _ = role
        return self._repositories

    def get_repository(self, workspace, name):
        return {
            "full_name": f"{workspace}/{name}",
            "links": {"clone": [{"name": "ssh", "href": "git@example.com:acme/example.git"}]},
            "is_archived": False,
            "mainbranch": {"name": "main"},
        }

    def list_branches(self, full_name):
        _ = full_name
        return self._branches


class _FakeGitSource:
    def __init__(self):
        self.calls = []

    def update_mirror(self, mirror_path):
        self.calls.append(("update_mirror", mirror_path))

    def clone_repo(self, clone_url, local_path, mirror=False):
        self.calls.append(("clone_repo", clone_url, local_path, mirror))
        return object()

    def fetch_working_copy(self, local_path):
        self.calls.append(("fetch_working_copy", local_path))
        return object()

    def checkout_branch(self, repo, branch_name):
        self.calls.append(("checkout_branch", branch_name))


class _MemoryLogger:
    log_format = "json"
    run_id = "run-test-memory"

    def __init__(self):
        self.events = []

    def event(self, action, outcome="info", level="INFO", message=None, **fields):
        event = {
            "action": action,
            "outcome": outcome,
            "level": level,
            "message": message,
        }
        event.update(fields)
        self.events.append(event)
        return event

    def close(self):
        return None


class TestDownloader(unittest.TestCase):
    def test_selected_modes(self):
        self.assertEqual(("mirror", "working"), downloader.selected_modes("both"))
        self.assertEqual(("mirror",), downloader.selected_modes("mirror"))
        self.assertEqual(("working",), downloader.selected_modes("working"))

    def test_parser_accepts_new_arguments(self):
        parser = downloader.build_parser()
        args = parser.parse_args(
            [
                "--provider",
                "bitbucket",
                "--mode",
                "mirror",
                "--output-dir",
                "./backups",
                "--snapshot-format",
                "zip",
                "--snapshot-dir",
                "./snapshots",
                "--retain-days",
                "30",
                "--retain-count",
                "10",
                "--role",
                "member",
                "--log-format",
                "json",
                "--log-file",
                "./logs/run.log",
                "--include",
                "acme/*",
                "--exclude",
                "acme/private-*",
                "--branch",
                "main",
                "--branch-pattern",
                "release/*",
                "--default-branch-only",
                "--repo-retries",
                "2",
                "--force-lock",
            ]
        )
        self.assertEqual("bitbucket", args.provider)
        self.assertEqual("backup", args.command)
        self.assertEqual("mirror", args.mode)
        self.assertEqual("./backups", args.output_dir)
        self.assertEqual("zip", args.snapshot_format)
        self.assertEqual("./snapshots", args.snapshot_dir)
        self.assertEqual(30, args.retain_days)
        self.assertEqual(10, args.retain_count)
        self.assertEqual("json", args.log_format)
        self.assertEqual("./logs/run.log", args.log_file)
        self.assertEqual(["acme/*"], args.include)
        self.assertEqual(["acme/private-*"], args.exclude)
        self.assertEqual(["main"], args.branch)
        self.assertEqual(["release/*"], args.branch_pattern)
        self.assertTrue(args.default_branch_only)
        self.assertEqual(2, args.repo_retries)
        self.assertTrue(args.force_lock)

    def test_parser_accepts_restore_commands(self):
        parser = downloader.build_parser()
        list_args = parser.parse_args(["list-backups", "--output-dir", "./backups"])
        self.assertEqual("list-backups", list_args.command)

        validate_args = parser.parse_args(
            [
                "validate-restore",
                "--backup-path",
                "./backups/bitbucket/acme/example.git",
                "--restore-dir",
                "./restore-test",
            ]
        )
        self.assertEqual("validate-restore", validate_args.command)
        self.assertEqual("./backups/bitbucket/acme/example.git", validate_args.backup_path)
        self.assertEqual("./restore-test", validate_args.restore_dir)

    def test_parser_accepts_repeatable_and_comma_separated_patterns(self):
        parser = downloader.build_parser()
        args = parser.parse_args(
            [
                "--include",
                "acme/*,other/*",
                "--include",
                "team/*",
                "--exclude",
                "acme/private-*",
                "--exclude",
                "other/legacy-*",
            ]
        )
        self.assertEqual(["acme/*,other/*", "team/*"], args.include)
        self.assertEqual(["acme/private-*", "other/legacy-*"], args.exclude)

    def test_parser_accepts_repeatable_branch_selectors(self):
        parser = downloader.build_parser()
        args = parser.parse_args(
            [
                "--branch",
                "main,dev",
                "--branch",
                "release",
                "--branch-pattern",
                "feature/*,hotfix/*",
                "--branch-pattern",
                "release/*",
            ]
        )
        self.assertEqual(["main,dev", "release"], args.branch)
        self.assertEqual(["feature/*,hotfix/*", "release/*"], args.branch_pattern)

    def test_resolve_token_from_environment(self):
        with patch.dict("os.environ", {"TOKEN_ENV_NAME": "secret-token"}, clear=False):
            with patch("getpass.getpass") as mock_getpass:
                token = downloader.resolve_token("TOKEN_ENV_NAME")
        self.assertEqual("secret-token", token)
        mock_getpass.assert_not_called()

    def test_resolve_token_falls_back_to_prompt(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("builtins.print"):
                with patch("getpass.getpass", return_value="prompt-token") as mock_getpass:
                    token = downloader.resolve_token("TOKEN_ENV_NAME")
        self.assertEqual("prompt-token", token)
        mock_getpass.assert_called_once()

    def test_create_provider_requires_username_for_bitbucket(self):
        args = argparse.Namespace(provider="bitbucket", username=None)
        with self.assertRaises(ProviderConfigurationError):
            downloader.create_provider(args, token="x")

    def test_run_backup_dry_run_does_not_call_git_source(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="both",
            dry_run=True,
            include=[],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )
        provider = _FakeProvider()
        git_source = _FakeGitSource()
        logger = _MemoryLogger()
        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["processed"])
        self.assertEqual(1, stats["succeeded"])
        self.assertEqual([], git_source.calls)
        logged_actions = [event["action"] for event in logger.events]
        self.assertIn("sync.mirror.clone", logged_actions)
        self.assertIn("sync.working.clone", logged_actions)
        self.assertIn("repository.finish", logged_actions)

    def test_run_backup_include_filter_skips_non_matching_repo(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="both",
            dry_run=True,
            include=["acme/*"],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )
        provider = _FakeProvider(
            repositories=[
                {"repository": {"full_name": "acme/example"}},
                {"repository": {"full_name": "other/skipme"}},
            ]
        )
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(2, stats["processed"])
        self.assertEqual(1, stats["succeeded"])
        self.assertEqual(1, stats["skipped"])
        self.assertEqual([], git_source.calls)
        skip_events = [event for event in logger.events if event["action"] == "repository.skip"]
        self.assertEqual(1, len(skip_events))
        self.assertEqual("include_miss", skip_events[0]["reason"])

    def test_run_backup_exclude_filter_overrides_include(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="both",
            dry_run=True,
            include=["acme/*"],
            exclude=["acme/example"],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )
        provider = _FakeProvider(repositories=[{"repository": {"full_name": "acme/example"}}])
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["processed"])
        self.assertEqual(0, stats["succeeded"])
        self.assertEqual(1, stats["skipped"])
        skip_events = [event for event in logger.events if event["action"] == "repository.skip"]
        self.assertEqual("exclude_match", skip_events[0]["reason"])

    def test_run_backup_exclude_only_filters_repository(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="both",
            dry_run=True,
            include=[],
            exclude=["other/*"],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )
        provider = _FakeProvider(
            repositories=[
                {"repository": {"full_name": "acme/example"}},
                {"repository": {"full_name": "other/skipme"}},
            ]
        )
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(2, stats["processed"])
        self.assertEqual(1, stats["succeeded"])
        self.assertEqual(1, stats["skipped"])
        skip_events = [event for event in logger.events if event["action"] == "repository.skip"]
        self.assertEqual("exclude_match", skip_events[0]["reason"])

    def test_run_backup_output_layout_is_consistent_across_providers(self):
        for provider_name in ("bitbucket", "github", "gitlab"):
            with self.subTest(provider=provider_name):
                args = SimpleNamespace(
                    workspace=None,
                    role="member",
                    include_archived=False,
                    output_dir="./backups-test",
                    provider=provider_name,
                    mode="both",
                    dry_run=True,
                    include=[],
                    exclude=[],
                    branch_names=[],
                    branch_patterns=[],
                    default_branch_only=False,
                    repo_retries=0,
                )
                provider = _FakeProvider()
                git_source = _FakeGitSource()
                logger = _MemoryLogger()

                stats = downloader.run_backup(args, provider, git_source, logger=logger)

                self.assertEqual(1, stats["processed"])
                self.assertEqual(1, stats["succeeded"])
                mirror_events = [
                    event for event in logger.events if event["action"] == "sync.mirror.clone"
                ]
                working_events = [
                    event for event in logger.events if event["action"] == "sync.working.clone"
                ]
                self.assertEqual(1, len(mirror_events))
                self.assertEqual(1, len(working_events))
                self.assertTrue(
                    mirror_events[0]["path"].endswith(f"/{provider_name}/acme/example.git")
                )
                self.assertTrue(
                    working_events[0]["path"].endswith(f"/{provider_name}/acme/example")
                )

    def test_run_backup_filter_parity_across_providers(self):
        repositories = [
            {"repository": {"full_name": "acme/private-service"}},
            {"repository": {"full_name": "acme/public-service"}},
        ]
        for provider_name in ("bitbucket", "github", "gitlab"):
            with self.subTest(provider=provider_name):
                args = SimpleNamespace(
                    workspace=None,
                    role="member",
                    include_archived=False,
                    output_dir="./backups-test",
                    provider=provider_name,
                    mode="both",
                    dry_run=True,
                    include=["acme/*"],
                    exclude=["acme/private-*"],
                    branch_names=[],
                    branch_patterns=[],
                    default_branch_only=False,
                    repo_retries=0,
                )
                provider = _FakeProvider(repositories=repositories)
                git_source = _FakeGitSource()
                logger = _MemoryLogger()

                stats = downloader.run_backup(args, provider, git_source, logger=logger)

                self.assertEqual(2, stats["processed"])
                self.assertEqual(1, stats["succeeded"])
                self.assertEqual(1, stats["skipped"])

    def test_run_backup_dry_run_plans_snapshot_export(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="mirror",
            dry_run=True,
            include=[],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
            snapshot_format="zip",
            snapshot_dir="./snapshots-test",
        )
        provider = _FakeProvider()
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["processed"])
        snapshot_events = [event for event in logger.events if event["action"] == "snapshot.create"]
        self.assertEqual(1, len(snapshot_events))
        self.assertEqual("planned", snapshot_events[0]["outcome"])
        self.assertTrue(snapshot_events[0]["path"].endswith(".zip"))

    def test_run_backup_creates_snapshot_after_mirror_sync(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="mirror",
            dry_run=False,
            include=[],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
            snapshot_format="tar.gz",
            snapshot_dir="./snapshots-test",
        )
        provider = _FakeProvider()
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        with patch(
            "downloader.create_snapshot_archive",
            return_value="./snapshots-test/bitbucket/acme/example.tar.gz",
        ) as mock_snapshot:
            stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["processed"])
        self.assertEqual(1, stats["succeeded"])
        self.assertEqual(1, mock_snapshot.call_count)

    def test_run_backup_dry_run_reports_retention_deletion(self):
        with tempfile.TemporaryDirectory() as snapshot_dir:
            workspace_dir = os.path.join(snapshot_dir, "bitbucket", "acme")
            os.makedirs(workspace_dir, exist_ok=True)
            snapshot_path = os.path.join(workspace_dir, "example-20200101T000000Z.zip")
            with open(snapshot_path, "w", encoding="utf-8") as snapshot_file:
                snapshot_file.write("old snapshot")
            os.utime(snapshot_path, (1, 1))

            args = SimpleNamespace(
                workspace=None,
                role="member",
                include_archived=False,
                output_dir="./backups-test",
                provider="bitbucket",
                mode="mirror",
                dry_run=True,
                include=[],
                exclude=[],
                branch_names=[],
                branch_patterns=[],
                default_branch_only=False,
                repo_retries=0,
                snapshot_format=None,
                snapshot_dir=snapshot_dir,
                retain_days=1,
                retain_count=None,
            )
            provider = _FakeProvider()
            git_source = _FakeGitSource()
            logger = _MemoryLogger()

            stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["processed"])
        retention_events = [
            event for event in logger.events if event["action"] == "retention.delete"
        ]
        self.assertEqual(1, len(retention_events))
        self.assertEqual("planned", retention_events[0]["outcome"])
        self.assertEqual("snapshot", retention_events[0]["artifact_type"])

    def test_json_logger_outputs_parseable_events_with_required_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test")
        with redirect_stdout(buffer):
            logger.event(
                "repository.start",
                outcome="start",
                provider="bitbucket",
                repository="acme/example",
                mode="both",
            )
        output_line = buffer.getvalue().strip()
        parsed = json.loads(output_line)

        self.assertEqual("repository.start", parsed["action"])
        self.assertEqual("start", parsed["outcome"])
        self.assertEqual("run-test", parsed["run_id"])
        self.assertEqual("bitbucket", parsed["provider"])
        self.assertEqual("acme/example", parsed["repository"])
        self.assertEqual("both", parsed["mode"])
        self.assertIn("timestamp", parsed)

    def test_json_logger_redacts_sensitive_fields(self):
        buffer = io.StringIO()
        logger = RunLogger(log_format="json", run_id="run-test-redaction")
        with redirect_stdout(buffer):
            logger.event(
                "run.start",
                outcome="start",
                token="super-secret-token",
                ssh_key_path="/Users/secret/.ssh/id_rsa",
                nested={"api_token": "another-secret"},
            )
        parsed = json.loads(buffer.getvalue().strip())

        self.assertEqual(REDACTED_VALUE, parsed["token"])
        self.assertEqual(REDACTED_VALUE, parsed["ssh_key_path"])
        self.assertEqual(REDACTED_VALUE, parsed["nested"]["api_token"])
        self.assertNotIn("super-secret-token", buffer.getvalue())

    def test_null_logger_default_paths_do_not_raise(self):
        token = "from-prompt"
        with patch.dict("os.environ", {}, clear=True):
            with patch("getpass.getpass", return_value=token):
                resolved = downloader.resolve_token(token_env=None, logger=None)
        self.assertEqual(token, resolved)

    def test_select_working_branches_by_name_and_pattern(self):
        branches = [
            {"name": "main"},
            {"name": "dev"},
            {"name": "release/1.0"},
            {"name": "feature/x"},
        ]
        selected = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["dev"],
            branch_patterns=["release/*"],
            default_branch_only=False,
            default_branch_name=None,
        )
        self.assertEqual(["dev", "release/1.0"], [branch["name"] for branch in selected])

    def test_select_working_branches_default_only(self):
        branches = [{"name": "main"}, {"name": "dev"}]
        selected = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["dev"],
            branch_patterns=["*"],
            default_branch_only=True,
            default_branch_name="main",
        )
        self.assertEqual(["main"], [branch["name"] for branch in selected])

    def test_run_backup_working_mode_respects_branch_selectors(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="working",
            dry_run=False,
            include=[],
            exclude=[],
            branch_names=["dev"],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )
        provider = _FakeProvider(
            branches=[
                {"name": "main"},
                {"name": "dev"},
                {"name": "release/1"},
            ]
        )
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["processed"])
        self.assertEqual(1, stats["succeeded"])
        checkout_calls = [call for call in git_source.calls if call[0] == "checkout_branch"]
        self.assertEqual([("checkout_branch", "dev")], checkout_calls)

    def test_run_backup_retries_repository_after_sync_failure(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="mirror",
            dry_run=False,
            include=[],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=1,
        )
        provider = _FakeProvider()
        logger = _MemoryLogger()

        class _FlakyGitSource(_FakeGitSource):
            def __init__(self):
                super().__init__()
                self._clone_attempts = 0

            def clone_repo(self, clone_url, local_path, mirror=False):
                self._clone_attempts += 1
                if self._clone_attempts == 1:
                    raise RepositorySyncError("Failed cloning repository from x")
                return super().clone_repo(clone_url, local_path, mirror=mirror)

        git_source = _FlakyGitSource()
        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["processed"])
        self.assertEqual(1, stats["succeeded"])
        self.assertEqual(0, stats["failed"])
        self.assertEqual(0, stats["failure_types"]["clone"])
        retry_events = [event for event in logger.events if event["action"] == "repository.retry"]
        self.assertEqual(1, len(retry_events))
        self.assertEqual("clone", retry_events[0]["failure_type"])

    def test_run_backup_failure_summary_classifies_auth_errors(self):
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="bitbucket",
            mode="mirror",
            dry_run=False,
            include=[],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )
        logger = _MemoryLogger()

        class _AuthFailProvider(_FakeProvider):
            def get_repository(self, workspace, name):
                _ = workspace
                _ = name
                raise AuthenticationError("token expired")

        provider = _AuthFailProvider()
        git_source = _FakeGitSource()
        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["failed"])
        self.assertEqual(1, stats["failure_types"]["auth"])
        self.assertEqual(0, stats["failure_types"]["api"])

    def test_main_fails_when_run_lock_is_active(self):
        with patch("downloader.acquire_run_lock", side_effect=RunLockError("lock active")):
            exit_code = downloader.main(
                [
                    "--provider",
                    "bitbucket",
                    "--username",
                    "my-user",
                    "--dry-run",
                ]
            )

        self.assertEqual(1, exit_code)

    def test_main_releases_lock_when_run_finishes(self):
        class _FakeProviderWithAuth:
            def auth_ok(self):
                return True

            @property
            def auth_error(self):
                return None

        class _FakeGitModule:
            class GitSource:
                def __init__(self, key_path):
                    self.key_path = key_path

        stats = {
            "processed": 1,
            "succeeded": 1,
            "skipped": 0,
            "failed": 0,
            "failure_types": downloader.make_failure_counters(),
        }
        with patch(
            "downloader.acquire_run_lock",
            return_value={
                "path": "/tmp/repo-downloader-test.lock",
                "replaced_stale": False,
                "replaced_forced": False,
            },
        ) as mock_acquire:
            with patch("downloader.release_run_lock") as mock_release:
                with patch("downloader.resolve_token", return_value="token-value"):
                    with patch(
                        "downloader.create_provider",
                        return_value=_FakeProviderWithAuth(),
                    ):
                        with patch("downloader.run_backup", return_value=stats):
                            with patch(
                                "downloader.importlib.import_module",
                                return_value=_FakeGitModule(),
                            ):
                                exit_code = downloader.main(
                                    [
                                        "--provider",
                                        "bitbucket",
                                        "--username",
                                        "my-user",
                                        "--token-env",
                                        "BB_TOKEN",
                                        "--dry-run",
                                    ]
                                )

        self.assertEqual(0, exit_code)
        mock_acquire.assert_called_once()
        mock_release.assert_called_once_with("/tmp/repo-downloader-test.lock")

    def test_main_list_backups_command_lists_entries(self):
        with tempfile.TemporaryDirectory() as output_dir:
            mirror_path = os.path.join(output_dir, "bitbucket", "acme", "example.git")
            working_path = os.path.join(output_dir, "bitbucket", "acme", "example")
            os.makedirs(mirror_path, exist_ok=True)
            os.makedirs(working_path, exist_ok=True)

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = downloader.main(["list-backups", "--output-dir", output_dir])

        output = buffer.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("Found 2 backup entries", output)
        self.assertIn("bitbucket/acme/example [mirror]", output)
        self.assertIn("bitbucket/acme/example [working]", output)

    def test_main_validate_restore_requires_backup_path(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = downloader.main(["validate-restore"])

        self.assertEqual(1, exit_code)
        self.assertIn("--backup-path is required", buffer.getvalue())

    def test_perform_restore_validation_checks_clone_and_refs(self):
        class _FakeRepoObject:
            heads = [SimpleNamespace(name="main")]
            remotes = SimpleNamespace(
                origin=SimpleNamespace(refs=[SimpleNamespace(name="origin/main")])
            )

        class _FakeRepoClass:
            @staticmethod
            def clone_from(source, destination):
                _ = source
                os.makedirs(destination, exist_ok=True)
                return _FakeRepoObject()

        fake_git_module = SimpleNamespace(Repo=_FakeRepoClass)
        fake_git_exc_module = SimpleNamespace(GitError=RuntimeError)

        def fake_import(module_name):
            if module_name == "git":
                return fake_git_module
            if module_name == "git.exc":
                return fake_git_exc_module
            raise ModuleNotFoundError(module_name)

        with tempfile.TemporaryDirectory() as tmp_dir:
            backup_path = os.path.join(tmp_dir, "repo.git")
            restore_dir = os.path.join(tmp_dir, "restore")
            os.makedirs(backup_path, exist_ok=True)

            with patch("downloader.importlib.import_module", side_effect=fake_import):
                result = downloader.perform_restore_validation(backup_path, restore_dir)

        self.assertEqual(1, result["branch_count"])
        self.assertEqual(1, result["remote_ref_count"])


class TestDownloaderEdgeCases(unittest.TestCase):
    def test_normalize_cli_list_handles_empty_input(self):
        result = downloader.normalize_cli_list(None)
        self.assertEqual([], result)

    def test_normalize_cli_list_handles_empty_list(self):
        result = downloader.normalize_cli_list([])
        self.assertEqual([], result)

    def test_normalize_cli_list_strips_whitespace(self):
        result = downloader.normalize_cli_list(["  value1  ", " value2 "])
        self.assertEqual(["value1", "value2"], result)

    def test_normalize_cli_list_handles_comma_separated_values(self):
        result = downloader.normalize_cli_list(["value1,value2", "value3"])
        self.assertEqual(["value1", "value2", "value3"], result)

    def test_normalize_cli_list_filters_empty_strings(self):
        result = downloader.normalize_cli_list(["value1,,value2", "", "  ", "value3"])
        self.assertEqual(["value1", "value2", "value3"], result)

    def test_classify_repository_failure_auth_error(self):
        result = downloader.classify_repository_failure(AuthenticationError("auth failed"))
        self.assertEqual("auth", result)

    def test_classify_repository_failure_api_error(self):
        result = downloader.classify_repository_failure(RemoteAPIError("api failed"))
        self.assertEqual("api", result)

    def test_classify_repository_failure_clone_error(self):
        result = downloader.classify_repository_failure(
            RepositorySyncError("Failed cloning repository")
        )
        self.assertEqual("clone", result)

    def test_classify_repository_failure_fetch_error(self):
        result = downloader.classify_repository_failure(
            RepositorySyncError("Failed fetching repository")
        )
        self.assertEqual("fetch", result)

    def test_classify_repository_failure_checkout_error(self):
        result = downloader.classify_repository_failure(
            RepositorySyncError("Failed checkout branch")
        )
        self.assertEqual("checkout", result)

    def test_classify_repository_failure_other_sync_error(self):
        result = downloader.classify_repository_failure(
            RepositorySyncError("Unknown sync error")
        )
        self.assertEqual("other", result)

    def test_classify_repository_failure_key_error(self):
        result = downloader.classify_repository_failure(KeyError("missing key"))
        self.assertEqual("api", result)

    def test_classify_repository_failure_type_error(self):
        result = downloader.classify_repository_failure(TypeError("type mismatch"))
        self.assertEqual("api", result)

    def test_classify_repository_failure_value_error(self):
        result = downloader.classify_repository_failure(ValueError("invalid value"))
        self.assertEqual("api", result)

    def test_classify_repository_failure_unknown_exception(self):
        result = downloader.classify_repository_failure(RuntimeError("runtime error"))
        self.assertEqual("other", result)

    def test_make_failure_counters_initializes_all_types(self):
        counters = downloader.make_failure_counters()
        expected_types = ("api", "auth", "clone", "fetch", "checkout", "other")
        for failure_type in expected_types:
            self.assertIn(failure_type, counters)
            self.assertEqual(0, counters[failure_type])

    def test_format_failure_counters_empty(self):
        counters = downloader.make_failure_counters()
        result = downloader.format_failure_counters(counters)
        self.assertEqual("none", result)

    def test_format_failure_counters_with_values(self):
        counters = {"api": 2, "auth": 0, "clone": 1, "fetch": 0, "checkout": 0, "other": 0}
        result = downloader.format_failure_counters(counters)
        self.assertIn("api=2", result)
        self.assertIn("clone=1", result)
        self.assertNotIn("auth=0", result)

    def test_get_default_branch_name_from_mainbranch_dict(self):
        repo = {"mainbranch": {"name": "master"}}
        result = downloader.get_default_branch_name(repo)
        self.assertEqual("master", result)

    def test_get_default_branch_name_from_default_branch_dict(self):
        repo = {"default_branch": {"name": "main"}}
        result = downloader.get_default_branch_name(repo)
        self.assertEqual("main", result)

    def test_get_default_branch_name_from_default_branch_string(self):
        repo = {"default_branch": "develop"}
        result = downloader.get_default_branch_name(repo)
        self.assertEqual("develop", result)

    def test_get_default_branch_name_prefers_mainbranch_over_default_branch(self):
        repo = {
            "mainbranch": {"name": "master"},
            "default_branch": {"name": "main"}
        }
        result = downloader.get_default_branch_name(repo)
        self.assertEqual("master", result)

    def test_get_default_branch_name_returns_none_for_non_dict(self):
        result = downloader.get_default_branch_name("not a dict")
        self.assertIsNone(result)

    def test_get_default_branch_name_returns_none_when_missing(self):
        repo = {"other_field": "value"}
        result = downloader.get_default_branch_name(repo)
        self.assertIsNone(result)

    def test_select_working_branches_empty_list(self):
        result = downloader.select_working_branches(
            branches=[],
            explicit_branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            default_branch_name=None
        )
        self.assertEqual([], result)

    def test_select_working_branches_default_only_without_default_name(self):
        branches = [{"name": "main"}, {"name": "dev"}]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=[],
            default_branch_only=True,
            default_branch_name=None
        )
        self.assertEqual([], result)

    def test_select_working_branches_no_filters_returns_all(self):
        branches = [{"name": "main"}, {"name": "dev"}]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            default_branch_name=None
        )
        self.assertEqual(2, len(result))

    def test_select_working_branches_filters_branches_without_name(self):
        branches = [{"name": "main"}, {"other": "field"}, {"name": "dev"}]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["main", "dev"],
            branch_patterns=[],
            default_branch_only=False,
            default_branch_name=None
        )
        self.assertEqual(["main", "dev"], [b["name"] for b in result])

    def test_select_working_branches_pattern_matching(self):
        branches = [
            {"name": "main"},
            {"name": "feature/A"},
            {"name": "feature/B"},
            {"name": "hotfix/C"}
        ]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=["feature/*"],
            default_branch_only=False,
            default_branch_name=None
        )
        self.assertEqual(["feature/A", "feature/B"], [b["name"] for b in result])

    def test_emit_text_prints_in_text_mode(self):
        logger = _MemoryLogger()
        logger.log_format = "text"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            downloader.emit_text(logger, "test message")
        self.assertEqual("test message\n", buffer.getvalue())

    def test_emit_text_does_not_print_in_json_mode(self):
        logger = _MemoryLogger()
        logger.log_format = "json"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            downloader.emit_text(logger, "test message")
        self.assertEqual("", buffer.getvalue())

    def test_list_backup_entries_returns_empty_for_missing_directory(self):
        entries = downloader.list_backup_entries("/nonexistent/path")
        self.assertEqual([], entries)

    def test_list_backup_entries_skips_non_directory_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            provider_path = os.path.join(tmp_dir, "bitbucket")
            os.makedirs(provider_path, exist_ok=True)
            # Create a file instead of directory
            with open(os.path.join(provider_path, "notadir.txt"), "w", encoding="utf-8") as f:
                f.write("test")

            entries = downloader.list_backup_entries(tmp_dir)
            self.assertEqual([], entries)

    def test_create_provider_unknown_provider_raises_error(self):
        args = argparse.Namespace(provider="unknown-provider", username="user")
        with self.assertRaises(ProviderConfigurationError) as context:
            downloader.create_provider(args, "token")
        self.assertIn("Unknown provider", str(context.exception))


class TestDownloaderRegressionTests(unittest.TestCase):
    """Regression tests for previously discovered issues."""

    def test_run_backup_handles_repository_with_no_ssh_url(self):
        """Ensure repositories without SSH clone URLs are skipped gracefully."""
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="github",
            mode="mirror",
            dry_run=False,
            include=[],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )

        class _ProviderWithoutSshUrl(_FakeProvider):
            def get_repository(self, workspace, name):
                return {
                    "full_name": f"{workspace}/{name}",
                    "links": {"clone": [{"name": "https", "href": "https://example.com"}]},
                }

        provider = _ProviderWithoutSshUrl()
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["skipped"])
        self.assertEqual(0, stats["succeeded"])
        skip_events = [e for e in logger.events if e["action"] == "repository.skip"]
        self.assertTrue(any("ssh" in str(e.get("reason", "")).lower() for e in skip_events))

    def test_run_backup_handles_provider_returning_none_repository(self):
        """Ensure proper error when provider returns None for repository details."""
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="github",
            mode="mirror",
            dry_run=False,
            include=[],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )

        class _ProviderReturningNone(_FakeProvider):
            def get_repository(self, workspace, name):
                return None

        provider = _ProviderReturningNone()
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["failed"])
        self.assertEqual(0, stats["succeeded"])

    def test_run_backup_handles_empty_branch_list(self):
        """Ensure working mode handles repositories with no branches."""
        args = SimpleNamespace(
            workspace=None,
            role="member",
            include_archived=False,
            output_dir="./backups-test",
            provider="github",
            mode="working",
            dry_run=True,  # Use dry run to avoid actual git operations
            include=[],
            exclude=[],
            branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            repo_retries=0,
        )

        # Provider returns empty branch list
        provider = _FakeProvider(branches=[])
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(1, stats["succeeded"])
        # Should not attempt to checkout any branches when list is empty
        checkout_calls = [c for c in git_source.calls if c[0] == "checkout_branch"]
        self.assertEqual([], checkout_calls)


if __name__ == "__main__":
    unittest.main()