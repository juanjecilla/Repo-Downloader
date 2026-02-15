import argparse
import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import downloader
from utils.errors import AuthenticationError, ProviderConfigurationError, RepositorySyncError
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
            ]
        )
        self.assertEqual("bitbucket", args.provider)
        self.assertEqual("mirror", args.mode)
        self.assertEqual("./backups", args.output_dir)
        self.assertEqual("json", args.log_format)
        self.assertEqual("./logs/run.log", args.log_file)
        self.assertEqual(["acme/*"], args.include)
        self.assertEqual(["acme/private-*"], args.exclude)
        self.assertEqual(["main"], args.branch)
        self.assertEqual(["release/*"], args.branch_pattern)
        self.assertTrue(args.default_branch_only)
        self.assertEqual(2, args.repo_retries)

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


class TestClassifyRepositoryFailure(unittest.TestCase):
    def test_classify_authentication_error(self):
        failure_type = downloader.classify_repository_failure(
            AuthenticationError("token expired")
        )
        self.assertEqual("auth", failure_type)

    def test_classify_remote_api_error(self):
        from utils.errors import RemoteAPIError

        failure_type = downloader.classify_repository_failure(RemoteAPIError("rate limit"))
        self.assertEqual("api", failure_type)

    def test_classify_checkout_error_from_message(self):
        failure_type = downloader.classify_repository_failure(
            RepositorySyncError("Failed checkout of branch 'main'")
        )
        self.assertEqual("checkout", failure_type)

    def test_classify_fetch_error_from_message(self):
        failure_type = downloader.classify_repository_failure(
            RepositorySyncError("Failed fetching working repository")
        )
        self.assertEqual("fetch", failure_type)

    def test_classify_clone_error_from_message(self):
        failure_type = downloader.classify_repository_failure(
            RepositorySyncError("Failed cloning repository")
        )
        self.assertEqual("clone", failure_type)

    def test_classify_repository_sync_error_without_keyword(self):
        failure_type = downloader.classify_repository_failure(
            RepositorySyncError("generic git error")
        )
        self.assertEqual("other", failure_type)

    def test_classify_key_error(self):
        failure_type = downloader.classify_repository_failure(KeyError("missing_field"))
        self.assertEqual("api", failure_type)

    def test_classify_type_error(self):
        failure_type = downloader.classify_repository_failure(TypeError("bad type"))
        self.assertEqual("api", failure_type)

    def test_classify_value_error(self):
        failure_type = downloader.classify_repository_failure(ValueError("invalid value"))
        self.assertEqual("api", failure_type)

    def test_classify_unknown_exception(self):
        failure_type = downloader.classify_repository_failure(RuntimeError("unexpected"))
        self.assertEqual("other", failure_type)


class TestGetDefaultBranchName(unittest.TestCase):
    def test_get_default_branch_name_from_mainbranch_dict(self):
        repo = {"mainbranch": {"name": "main"}}
        branch_name = downloader.get_default_branch_name(repo)
        self.assertEqual("main", branch_name)

    def test_get_default_branch_name_from_default_branch_dict(self):
        repo = {"default_branch": {"name": "develop"}}
        branch_name = downloader.get_default_branch_name(repo)
        self.assertEqual("develop", branch_name)

    def test_get_default_branch_name_from_default_branch_string(self):
        repo = {"default_branch": "master"}
        branch_name = downloader.get_default_branch_name(repo)
        self.assertEqual("master", branch_name)

    def test_get_default_branch_name_prefers_mainbranch_over_default_branch(self):
        repo = {"mainbranch": {"name": "main"}, "default_branch": {"name": "master"}}
        branch_name = downloader.get_default_branch_name(repo)
        self.assertEqual("main", branch_name)

    def test_get_default_branch_name_returns_none_when_missing(self):
        repo = {"full_name": "acme/repo"}
        branch_name = downloader.get_default_branch_name(repo)
        self.assertIsNone(branch_name)

    def test_get_default_branch_name_returns_none_when_not_dict(self):
        branch_name = downloader.get_default_branch_name("not-a-dict")
        self.assertIsNone(branch_name)

    def test_get_default_branch_name_handles_empty_name(self):
        repo = {"mainbranch": {"name": ""}}
        branch_name = downloader.get_default_branch_name(repo)
        self.assertIsNone(branch_name)


class TestNormalizeCliList(unittest.TestCase):
    def test_normalize_cli_list_with_comma_separated_values(self):
        result = downloader.normalize_cli_list(["a,b,c"])
        self.assertEqual(["a", "b", "c"], result)

    def test_normalize_cli_list_with_repeated_values(self):
        result = downloader.normalize_cli_list(["a", "b", "c"])
        self.assertEqual(["a", "b", "c"], result)

    def test_normalize_cli_list_with_mixed_comma_and_repeated(self):
        result = downloader.normalize_cli_list(["a,b", "c", "d,e"])
        self.assertEqual(["a", "b", "c", "d", "e"], result)

    def test_normalize_cli_list_strips_whitespace(self):
        result = downloader.normalize_cli_list(["  a  ,  b  ", "  c  "])
        self.assertEqual(["a", "b", "c"], result)

    def test_normalize_cli_list_skips_empty_values(self):
        result = downloader.normalize_cli_list(["a,,b", "", "c"])
        self.assertEqual(["a", "b", "c"], result)

    def test_normalize_cli_list_returns_empty_for_none(self):
        result = downloader.normalize_cli_list(None)
        self.assertEqual([], result)

    def test_normalize_cli_list_returns_empty_for_empty_list(self):
        result = downloader.normalize_cli_list([])
        self.assertEqual([], result)


class TestMakeFailureCounters(unittest.TestCase):
    def test_make_failure_counters_initializes_all_types(self):
        counters = downloader.make_failure_counters()
        self.assertEqual(0, counters["api"])
        self.assertEqual(0, counters["auth"])
        self.assertEqual(0, counters["clone"])
        self.assertEqual(0, counters["fetch"])
        self.assertEqual(0, counters["checkout"])
        self.assertEqual(0, counters["other"])


class TestFormatFailureCounters(unittest.TestCase):
    def test_format_failure_counters_with_multiple_types(self):
        counters = {"api": 2, "auth": 0, "clone": 1, "fetch": 0, "checkout": 0, "other": 3}
        formatted = downloader.format_failure_counters(counters)
        self.assertEqual("api=2, clone=1, other=3", formatted)

    def test_format_failure_counters_with_no_failures(self):
        counters = {"api": 0, "auth": 0, "clone": 0, "fetch": 0, "checkout": 0, "other": 0}
        formatted = downloader.format_failure_counters(counters)
        self.assertEqual("none", formatted)

    def test_format_failure_counters_respects_order(self):
        counters = {"other": 1, "api": 2, "auth": 3, "clone": 0, "fetch": 0, "checkout": 0}
        formatted = downloader.format_failure_counters(counters)
        self.assertEqual("api=2, auth=3, other=1", formatted)


class TestEmitText(unittest.TestCase):
    def test_emit_text_prints_for_text_logger(self):
        from utils.log_utils import NullLogger

        logger = NullLogger()
        logger.log_format = "text"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            downloader.emit_text(logger, "test message")
        self.assertEqual("test message\n", buffer.getvalue())

    def test_emit_text_does_not_print_for_json_logger(self):
        from utils.log_utils import NullLogger

        logger = NullLogger()
        logger.log_format = "json"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            downloader.emit_text(logger, "test message")
        self.assertEqual("", buffer.getvalue())


class TestSelectWorkingBranches(unittest.TestCase):
    def test_select_working_branches_returns_empty_for_empty_input(self):
        result = downloader.select_working_branches(
            branches=[],
            explicit_branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            default_branch_name=None,
        )
        self.assertEqual([], result)

    def test_select_working_branches_default_only_filters_correctly(self):
        branches = [{"name": "main"}, {"name": "dev"}, {"name": "feature"}]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=[],
            default_branch_only=True,
            default_branch_name="main",
        )
        self.assertEqual([{"name": "main"}], result)

    def test_select_working_branches_default_only_returns_empty_without_default(self):
        branches = [{"name": "main"}, {"name": "dev"}]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=[],
            default_branch_only=True,
            default_branch_name=None,
        )
        self.assertEqual([], result)

    def test_select_working_branches_returns_all_without_filters(self):
        branches = [{"name": "main"}, {"name": "dev"}, {"name": "feature"}]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=[],
            default_branch_only=False,
            default_branch_name=None,
        )
        self.assertEqual(branches, result)

    def test_select_working_branches_filters_by_explicit_names(self):
        branches = [{"name": "main"}, {"name": "dev"}, {"name": "feature"}]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["dev", "feature"],
            branch_patterns=[],
            default_branch_only=False,
            default_branch_name=None,
        )
        self.assertEqual([{"name": "dev"}, {"name": "feature"}], result)

    def test_select_working_branches_filters_by_patterns(self):
        branches = [
            {"name": "main"},
            {"name": "feature/x"},
            {"name": "feature/y"},
            {"name": "hotfix/z"},
        ]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=["feature/*"],
            default_branch_only=False,
            default_branch_name=None,
        )
        self.assertEqual([{"name": "feature/x"}, {"name": "feature/y"}], result)

    def test_select_working_branches_combines_names_and_patterns(self):
        branches = [
            {"name": "main"},
            {"name": "dev"},
            {"name": "feature/x"},
            {"name": "hotfix/z"},
        ]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["main"],
            branch_patterns=["feature/*"],
            default_branch_only=False,
            default_branch_name=None,
        )
        self.assertEqual([{"name": "main"}, {"name": "feature/x"}], result)

    def test_select_working_branches_skips_branches_without_name(self):
        branches = [{"name": "main"}, {"invalid": "branch"}, {"name": "dev"}]
        result = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=["*"],
            default_branch_only=False,
            default_branch_name=None,
        )
        self.assertEqual([{"name": "main"}, {"name": "dev"}], result)


class TestMainErrorHandling(unittest.TestCase):
    def test_main_exits_with_error_for_negative_repo_retries(self):
        with self.assertRaises(SystemExit):
            downloader.main(["--repo-retries", "-1"])

    def test_main_normalizes_include_patterns(self):
        with patch("downloader.resolve_token", return_value="token"):
            with patch("downloader.create_provider"):
                with patch("downloader.importlib.import_module"):
                    parser = downloader.build_parser()
                    args = parser.parse_args(["--include", "A/*, B/*"])
                    args = downloader.main.__wrapped__ if hasattr(downloader.main, "__wrapped__") else None
                    if args:
                        normalized = downloader.normalize_repo_patterns(["A/*, B/*"])
                        self.assertEqual(["a/*", "b/*"], normalized)


if __name__ == "__main__":
    unittest.main()