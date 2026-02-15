# pylint: disable=too-many-lines

import argparse
import importlib.util
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
    REDACTED_TEXT,
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


class TestDownloader(unittest.TestCase):  # pylint: disable=too-many-public-methods
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
                "--config",
                "./profiles/daily.toml",
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
                "--summary-file",
                "./reports/summary.json",
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
                "--workers",
                "3",
                "--force-lock",
                "--resume",
            ]
        )
        self.assertEqual("bitbucket", args.provider)
        self.assertEqual("backup", args.command)
        self.assertEqual("./profiles/daily.toml", args.config)
        self.assertEqual("mirror", args.mode)
        self.assertEqual("./backups", args.output_dir)
        self.assertEqual("zip", args.snapshot_format)
        self.assertEqual("./snapshots", args.snapshot_dir)
        self.assertEqual(30, args.retain_days)
        self.assertEqual(10, args.retain_count)
        self.assertEqual("json", args.log_format)
        self.assertEqual("./logs/run.log", args.log_file)
        self.assertEqual("./reports/summary.json", args.summary_file)
        self.assertEqual(["acme/*"], args.include)
        self.assertEqual(["acme/private-*"], args.exclude)
        self.assertEqual(["main"], args.branch)
        self.assertEqual(["release/*"], args.branch_pattern)
        self.assertTrue(args.default_branch_only)
        self.assertEqual(2, args.repo_retries)
        self.assertEqual(3, args.workers)
        self.assertTrue(args.force_lock)
        self.assertTrue(args.resume)

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

    def test_apply_config_defaults_applies_when_cli_uses_defaults(self):
        parser = downloader.build_parser()
        args = parser.parse_args([])
        configured = downloader.apply_config_defaults(
            parser,
            args,
            {
                "provider": "github",
                "mode": "mirror",
                "include": ["acme/*"],
                "dry_run": True,
            },
        )

        self.assertEqual("github", configured.provider)
        self.assertEqual("mirror", configured.mode)
        self.assertEqual(["acme/*"], configured.include)
        self.assertTrue(configured.dry_run)

    def test_apply_config_defaults_preserves_cli_overrides(self):
        parser = downloader.build_parser()
        args = parser.parse_args(["--provider", "gitlab", "--mode", "working"])
        configured = downloader.apply_config_defaults(
            parser,
            args,
            {"provider": "github", "mode": "mirror"},
        )

        self.assertEqual("gitlab", configured.provider)
        self.assertEqual("working", configured.mode)

    def test_load_config_file_from_toml_profile(self):
        toml_available = importlib.util.find_spec("tomllib") is not None
        tomli_available = importlib.util.find_spec("tomli") is not None
        if not toml_available and not tomli_available:
            self.skipTest("toml parser dependency not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "backup.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(
                    '[backup]\nprovider = "github"\nmode = "mirror"\ninclude = ["acme/*"]\n'
                )

            loaded = downloader.load_config_file(config_path)

        self.assertEqual("github", loaded["provider"])
        self.assertEqual("mirror", loaded["mode"])
        self.assertEqual(["acme/*"], loaded["include"])

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
        self.assertIn("mode_duration_ms", stats)
        self.assertIn("mirror", stats["mode_duration_ms"])
        self.assertIn("working", stats["mode_duration_ms"])

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
                mirror_path = os.path.normpath(mirror_events[0]["path"])
                working_path = os.path.normpath(working_events[0]["path"])
                self.assertTrue(
                    mirror_path.endswith(os.path.join(provider_name, "acme", "example.git"))
                )
                self.assertTrue(
                    working_path.endswith(os.path.join(provider_name, "acme", "example"))
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

    def test_run_backup_workers_parallelizes_repositories(self):
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
            workers=2,
        )
        provider = _FakeProvider(
            repositories=[
                {"repository": {"full_name": "acme/one"}},
                {"repository": {"full_name": "acme/two"}},
            ]
        )
        git_source = _FakeGitSource()
        logger = _MemoryLogger()

        stats = downloader.run_backup(args, provider, git_source, logger=logger)

        self.assertEqual(2, stats["processed"])
        self.assertEqual(2, stats["succeeded"])
        concurrent_events = [
            event for event in logger.events if event["action"] == "repositories.concurrent"
        ]
        self.assertEqual(1, len(concurrent_events))

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

    def test_run_backup_resume_skips_completed_repositories(self):
        with tempfile.TemporaryDirectory() as output_dir:
            checkpoint_dir = os.path.join(output_dir, "bitbucket")
            os.makedirs(checkpoint_dir, exist_ok=True)
            checkpoint_path = os.path.join(checkpoint_dir, ".repo-downloader-checkpoint.json")
            with open(checkpoint_path, "w", encoding="utf-8") as checkpoint_file:
                json.dump(
                    {
                        "signature": {
                            "provider": "bitbucket",
                            "mode": "mirror",
                            "workspace": None,
                            "include": [],
                            "exclude": [],
                        },
                        "completed": ["acme/one"],
                    },
                    checkpoint_file,
                )

            args = SimpleNamespace(
                workspace=None,
                role="member",
                include_archived=False,
                output_dir=output_dir,
                provider="bitbucket",
                mode="mirror",
                dry_run=False,
                include=[],
                exclude=[],
                branch_names=[],
                branch_patterns=[],
                default_branch_only=False,
                repo_retries=0,
                snapshot_format=None,
                snapshot_dir="./snapshots-test",
                retain_days=None,
                retain_count=None,
                resume=True,
            )
            provider = _FakeProvider(
                repositories=[
                    {"repository": {"full_name": "acme/one"}},
                    {"repository": {"full_name": "acme/two"}},
                ]
            )
            git_source = _FakeGitSource()
            logger = _MemoryLogger()

            stats = downloader.run_backup(args, provider, git_source, logger=logger)
            checkpoint_exists_after = os.path.exists(checkpoint_path)

        self.assertEqual(2, stats["processed"])
        self.assertEqual(1, stats["skipped"])
        self.assertEqual(1, stats["succeeded"])
        self.assertEqual(1, len([call for call in git_source.calls if call[0] == "clone_repo"]))
        self.assertFalse(checkpoint_exists_after)

    def test_run_backup_resume_keeps_checkpoint_on_failure(self):
        with tempfile.TemporaryDirectory() as output_dir:
            args = SimpleNamespace(
                workspace=None,
                role="member",
                include_archived=False,
                output_dir=output_dir,
                provider="bitbucket",
                mode="mirror",
                dry_run=False,
                include=[],
                exclude=[],
                branch_names=[],
                branch_patterns=[],
                default_branch_only=False,
                repo_retries=0,
                snapshot_format=None,
                snapshot_dir="./snapshots-test",
                retain_days=None,
                retain_count=None,
                resume=True,
            )

            class _FailingProvider(_FakeProvider):
                def get_repository(self, workspace, name):
                    _ = workspace
                    _ = name
                    raise AuthenticationError("token expired")

            provider = _FailingProvider()
            git_source = _FakeGitSource()
            logger = _MemoryLogger()

            stats = downloader.run_backup(args, provider, git_source, logger=logger)
            checkpoint_path = os.path.join(
                output_dir,
                "bitbucket",
                ".repo-downloader-checkpoint.json",
            )
            checkpoint_exists_after = os.path.exists(checkpoint_path)

        self.assertEqual(1, stats["failed"])
        self.assertTrue(checkpoint_exists_after)

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

    def test_sanitize_error_text_redacts_token_content(self):
        secret_value = "super-secret-token"
        sanitized = downloader.sanitize_error_text(
            f"authentication failed token={secret_value}",
            sensitive_values=[secret_value],
        )

        self.assertNotIn(secret_value, sanitized)
        self.assertIn(REDACTED_TEXT, sanitized)

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

    def test_main_redacts_secret_in_error_output(self):
        secret_value = "my-secret-token"
        with patch(
            "downloader.acquire_run_lock",
            return_value={
                "path": "/tmp/repo-downloader-test.lock",
                "replaced_stale": False,
                "replaced_forced": False,
            },
        ):
            with patch("downloader.release_run_lock"):
                with patch("downloader.resolve_token", return_value=secret_value):
                    with patch(
                        "downloader.create_provider",
                        side_effect=ProviderConfigurationError(
                            f"invalid credentials token={secret_value}"
                        ),
                    ):
                        buffer = io.StringIO()
                        with redirect_stdout(buffer):
                            exit_code = downloader.main(
                                [
                                    "--provider",
                                    "bitbucket",
                                    "--username",
                                    "my-user",
                                ]
                            )

        rendered = buffer.getvalue()
        self.assertEqual(1, exit_code)
        self.assertNotIn(secret_value, rendered)
        self.assertIn(REDACTED_TEXT, rendered)

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
            "mode_duration_ms": {"mirror": 0, "working": 0},
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

    def test_main_summary_includes_compatibility_report(self):
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
            "mode_duration_ms": {"mirror": 0, "working": 0},
        }
        compatibility_report = {
            "python_version": "3.11.8",
            "minimum_python_version": "3.8",
            "python_supported": True,
            "platform": "linux",
            "supported_platforms": ["linux", "macos", "windows"],
            "platform_supported": True,
            "git_version_raw": "git version 2.44.0",
            "git_version": "2.44.0",
            "minimum_git_version": "2.30.0",
            "git_supported": True,
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            summary_path = os.path.join(tmp_dir, "summary.json")
            with patch(
                "downloader.acquire_run_lock",
                return_value={
                    "path": os.path.join(tmp_dir, "repo-downloader.lock"),
                    "replaced_stale": False,
                    "replaced_forced": False,
                },
            ):
                with patch("downloader.release_run_lock"):
                    with patch("downloader.resolve_token", return_value="token-value"):
                        with patch(
                            "downloader.create_provider",
                            return_value=_FakeProviderWithAuth(),
                        ):
                            with patch("downloader.run_backup", return_value=stats):
                                with patch(
                                    "downloader.build_runtime_compatibility_report",
                                    return_value=compatibility_report,
                                ):
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
                                                "--summary-file",
                                                summary_path,
                                            ]
                                        )

            self.assertEqual(0, exit_code)
            with open(summary_path, "r", encoding="utf-8") as summary_file:
                payload = json.load(summary_file)
            self.assertEqual(compatibility_report, payload["compatibility"])

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

    def test_write_summary_report_creates_json_file(self):
        payload = {
            "provider": "bitbucket",
            "mode": "both",
            "processed": 2,
            "succeeded": 2,
            "failed": 0,
            "failure_types": downloader.make_failure_counters(),
            "mode_duration_ms": {"mirror": 15, "working": 20},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            summary_path = os.path.join(tmp_dir, "summary.json")
            written_path = downloader.write_summary_report(summary_path, payload)
            with open(written_path, "r", encoding="utf-8") as summary_file:
                loaded = json.load(summary_file)

        self.assertEqual(payload["provider"], loaded["provider"])
        self.assertEqual(payload["mode_duration_ms"], loaded["mode_duration_ms"])


if __name__ == "__main__":
    unittest.main()
