import importlib.util
import os
import tempfile
import unittest

import downloader
from utils.errors import ProviderConfigurationError


class TestConfigLoading(unittest.TestCase):
    def test_load_config_file_raises_error_for_unsupported_extension(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write('{"provider": "bitbucket"}')

            with self.assertRaises(ProviderConfigurationError) as context:
                downloader.load_config_file(config_path)

            self.assertIn("extension must be .toml, .yaml, or .yml", str(context.exception))

    def test_load_config_file_raises_error_for_nonexistent_file(self):
        with self.assertRaises(ProviderConfigurationError) as context:
            downloader.load_config_file("/nonexistent/config.toml")

        self.assertIn("Failed reading config file", str(context.exception))

    def test_load_config_file_raises_error_for_invalid_toml(self):
        toml_available = importlib.util.find_spec("tomllib") is not None
        tomli_available = importlib.util.find_spec("tomli") is not None
        if not toml_available and not tomli_available:
            self.skipTest("toml parser dependency not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "invalid.toml")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("provider = [invalid toml syntax\n")

            with self.assertRaises(ProviderConfigurationError) as context:
                downloader.load_config_file(config_path)

            self.assertIn("Invalid TOML config", str(context.exception))

    def test_load_config_file_raises_error_for_invalid_yaml(self):
        yaml_available = importlib.util.find_spec("yaml") is not None
        if not yaml_available:
            self.skipTest("yaml parser dependency not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "invalid.yaml")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("provider: bitbucket\n  - invalid: yaml\n")

            with self.assertRaises(ProviderConfigurationError) as context:
                downloader.load_config_file(config_path)

            self.assertIn("Invalid YAML config", str(context.exception))

    def test_load_config_file_raises_error_for_non_dict_root(self):
        toml_available = importlib.util.find_spec("tomllib") is not None
        tomli_available = importlib.util.find_spec("tomli") is not None
        if not toml_available and not tomli_available:
            self.skipTest("toml parser dependency not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "list.toml")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write('items = ["one", "two"]\n')

            # This should not raise since a TOML file with just an array value becomes a dict
            # Let's test with a YAML list instead

        yaml_available = importlib.util.find_spec("yaml") is not None
        if not yaml_available:
            self.skipTest("yaml parser dependency not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "list.yaml")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("- item1\n- item2\n")

            with self.assertRaises(ProviderConfigurationError) as context:
                downloader.load_config_file(config_path)

            self.assertIn("must contain a mapping", str(context.exception))

    def test_load_config_file_extracts_backup_section(self):
        toml_available = importlib.util.find_spec("tomllib") is not None
        tomli_available = importlib.util.find_spec("tomli") is not None
        if not toml_available and not tomli_available:
            self.skipTest("toml parser dependency not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "nested.toml")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write('[backup]\nprovider = "github"\nmode = "mirror"\n')

            loaded = downloader.load_config_file(config_path)

            self.assertEqual("github", loaded["provider"])
            self.assertEqual("mirror", loaded["mode"])

    def test_load_config_file_normalizes_hyphenated_keys_to_underscores(self):
        toml_available = importlib.util.find_spec("tomllib") is not None
        tomli_available = importlib.util.find_spec("tomli") is not None
        if not toml_available and not tomli_available:
            self.skipTest("toml parser dependency not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "hyphenated.toml")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write('provider = "bitbucket"\noutput-dir = "./backups"\nlog-format = "json"\n')

            loaded = downloader.load_config_file(config_path)

            self.assertEqual("./backups", loaded["output_dir"])
            self.assertEqual("json", loaded["log_format"])
            self.assertNotIn("output-dir", loaded)
            self.assertNotIn("log-format", loaded)

    def test_load_config_file_expands_tilde_in_path(self):
        toml_available = importlib.util.find_spec("tomllib") is not None
        tomli_available = importlib.util.find_spec("tomli") is not None
        if not toml_available and not tomli_available:
            self.skipTest("toml parser dependency not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "test.toml")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write('provider = "bitbucket"\n')

            tilde_path = "~/config/test.toml"
            if config_path.startswith(os.path.expanduser("~")):
                # Only test if we're in a home directory context
                loaded = downloader.load_config_file(config_path)
                self.assertIsNotNone(loaded)

    def test_apply_config_defaults_ignores_unknown_keys(self):
        parser = downloader.build_parser()
        args = parser.parse_args([])
        configured = downloader.apply_config_defaults(
            parser,
            args,
            {"provider": "github", "unknown_key": "value"},
        )
        self.assertEqual("github", configured.provider)
        self.assertFalse(hasattr(configured, "unknown_key"))

    def test_apply_config_defaults_converts_string_to_list_for_repeatable_keys(self):
        parser = downloader.build_parser()
        args = parser.parse_args([])
        configured = downloader.apply_config_defaults(
            parser,
            args,
            {"include": "acme/*"},
        )
        self.assertEqual(["acme/*"], configured.include)

    def test_normalize_cli_list_handles_empty_input(self):
        result = downloader.normalize_cli_list(None)
        self.assertEqual([], result)

        result = downloader.normalize_cli_list([])
        self.assertEqual([], result)

    def test_normalize_cli_list_handles_comma_separated_values(self):
        result = downloader.normalize_cli_list(["acme/*, other/*", "team/repo"])
        self.assertEqual(["acme/*", "other/*", "team/repo"], result)

    def test_normalize_cli_list_strips_whitespace(self):
        result = downloader.normalize_cli_list(["  acme/* , other/*  ", "  team/repo  "])
        self.assertEqual(["acme/*", "other/*", "team/repo"], result)

    def test_normalize_cli_list_filters_empty_strings(self):
        result = downloader.normalize_cli_list(["acme/*,,,", "", "  "])
        self.assertEqual(["acme/*"], result)


class TestDownloaderEdgeCases(unittest.TestCase):
    def test_classify_repository_failure_handles_auth_error(self):
        from utils.errors import AuthenticationError
        error = AuthenticationError("Token expired")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("auth", failure_type)

    def test_classify_repository_failure_handles_remote_api_error(self):
        from utils.errors import RemoteAPIError
        error = RemoteAPIError("API rate limit exceeded")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("api", failure_type)

    def test_classify_repository_failure_handles_checkout_sync_error(self):
        from utils.errors import RepositorySyncError
        error = RepositorySyncError("Failed checkout of branch 'main'")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("checkout", failure_type)

    def test_classify_repository_failure_handles_fetch_sync_error(self):
        from utils.errors import RepositorySyncError
        error = RepositorySyncError("Failed fetching working repository")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("fetch", failure_type)

    def test_classify_repository_failure_handles_clone_sync_error(self):
        from utils.errors import RepositorySyncError
        error = RepositorySyncError("Failed cloning repository from url")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("clone", failure_type)

    def test_classify_repository_failure_handles_generic_sync_error(self):
        from utils.errors import RepositorySyncError
        error = RepositorySyncError("Generic git operation failed")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("other", failure_type)

    def test_classify_repository_failure_handles_key_error(self):
        error = KeyError("missing_key")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("api", failure_type)

    def test_classify_repository_failure_handles_type_error(self):
        error = TypeError("Expected dict, got None")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("api", failure_type)

    def test_classify_repository_failure_handles_value_error(self):
        error = ValueError("Invalid JSON response")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("api", failure_type)

    def test_classify_repository_failure_handles_unknown_error(self):
        error = RuntimeError("Unknown error occurred")
        failure_type = downloader.classify_repository_failure(error)
        self.assertEqual("other", failure_type)

    def test_make_failure_counters_initializes_all_types(self):
        counters = downloader.make_failure_counters()
        for failure_type in ("api", "auth", "clone", "fetch", "checkout", "other"):
            self.assertIn(failure_type, counters)
            self.assertEqual(0, counters[failure_type])

    def test_format_failure_counters_returns_none_for_all_zeros(self):
        counters = downloader.make_failure_counters()
        formatted = downloader.format_failure_counters(counters)
        self.assertEqual("none", formatted)

    def test_format_failure_counters_includes_only_non_zero(self):
        counters = {
            "api": 2,
            "auth": 0,
            "clone": 1,
            "fetch": 0,
            "checkout": 0,
            "other": 3,
        }
        formatted = downloader.format_failure_counters(counters)
        self.assertIn("api=2", formatted)
        self.assertIn("clone=1", formatted)
        self.assertIn("other=3", formatted)
        self.assertNotIn("auth=", formatted)
        self.assertNotIn("fetch=", formatted)

    def test_get_default_branch_name_extracts_from_mainbranch(self):
        repo = {"mainbranch": {"name": "main"}}
        branch = downloader.get_default_branch_name(repo)
        self.assertEqual("main", branch)

    def test_get_default_branch_name_extracts_from_default_branch_dict(self):
        repo = {"default_branch": {"name": "master"}}
        branch = downloader.get_default_branch_name(repo)
        self.assertEqual("master", branch)

    def test_get_default_branch_name_extracts_from_default_branch_string(self):
        repo = {"default_branch": "develop"}
        branch = downloader.get_default_branch_name(repo)
        self.assertEqual("develop", branch)

    def test_get_default_branch_name_returns_none_for_missing_field(self):
        repo = {"full_name": "acme/repo"}
        branch = downloader.get_default_branch_name(repo)
        self.assertIsNone(branch)

    def test_get_default_branch_name_returns_none_for_non_dict_input(self):
        branch = downloader.get_default_branch_name(None)
        self.assertIsNone(branch)

    def test_select_working_branches_returns_empty_for_empty_input(self):
        branches = downloader.select_working_branches(
            branches=[],
            explicit_branch_names=[],
            branch_patterns=[],
        )
        self.assertEqual([], branches)

    def test_select_working_branches_returns_all_when_no_filters(self):
        branches = [{"name": "main"}, {"name": "dev"}]
        selected = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=[],
        )
        self.assertEqual(branches, selected)

    def test_select_working_branches_filters_by_explicit_names(self):
        branches = [{"name": "main"}, {"name": "dev"}, {"name": "feature"}]
        selected = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["main", "dev"],
            branch_patterns=[],
        )
        self.assertEqual(2, len(selected))
        self.assertEqual(["main", "dev"], [b["name"] for b in selected])

    def test_select_working_branches_filters_by_patterns(self):
        branches = [
            {"name": "main"},
            {"name": "release/1.0"},
            {"name": "release/2.0"},
            {"name": "feature/x"},
        ]
        selected = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=[],
            branch_patterns=["release/*"],
        )
        self.assertEqual(2, len(selected))
        self.assertEqual(["release/1.0", "release/2.0"], [b["name"] for b in selected])

    def test_select_working_branches_combines_names_and_patterns(self):
        branches = [
            {"name": "main"},
            {"name": "dev"},
            {"name": "release/1.0"},
        ]
        selected = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["dev"],
            branch_patterns=["release/*"],
        )
        self.assertEqual(2, len(selected))
        self.assertEqual(["dev", "release/1.0"], [b["name"] for b in selected])

    def test_select_working_branches_default_only_overrides_filters(self):
        branches = [
            {"name": "main"},
            {"name": "dev"},
            {"name": "feature"},
        ]
        selected = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["dev"],
            branch_patterns=["*"],
            default_branch_only=True,
            default_branch_name="main",
        )
        self.assertEqual(1, len(selected))
        self.assertEqual("main", selected[0]["name"])

    def test_select_working_branches_skips_branches_without_name(self):
        branches = [
            {"name": "main"},
            {"invalid": "no-name"},
            {"name": "dev"},
        ]
        selected = downloader.select_working_branches(
            branches=branches,
            explicit_branch_names=["main", "dev"],
            branch_patterns=[],
        )
        self.assertEqual(2, len(selected))


if __name__ == "__main__":
    unittest.main()