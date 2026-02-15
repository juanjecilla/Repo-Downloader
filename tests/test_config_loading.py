import importlib.util
import os
import tempfile
import unittest

from utils.errors import ProviderConfigurationError


TOML_AVAILABLE = (
    importlib.util.find_spec("tomllib") is not None
    or importlib.util.find_spec("tomli") is not None
)
YAML_AVAILABLE = importlib.util.find_spec("yaml") is not None


class TestConfigLoading(unittest.TestCase):
    @unittest.skipUnless(TOML_AVAILABLE, "TOML parser is required")
    def test_load_toml_config_parses_backup_section(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(
                    """
[backup]
provider = "github"
mode = "mirror"
workspace = "acme"
"""
                )

            config = downloader.load_config_file(config_path)

        self.assertEqual("github", config["provider"])
        self.assertEqual("mirror", config["mode"])
        self.assertEqual("acme", config["workspace"])

    @unittest.skipUnless(TOML_AVAILABLE, "TOML parser is required")
    def test_load_toml_config_normalizes_hyphenated_keys(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(
                    """
[backup]
output-dir = "./backups"
snapshot-format = "zip"
include-archived = true
"""
                )

            config = downloader.load_config_file(config_path)

        self.assertEqual("./backups", config["output_dir"])
        self.assertEqual("zip", config["snapshot_format"])
        self.assertTrue(config["include_archived"])

    @unittest.skipUnless(YAML_AVAILABLE, "PyYAML is required")
    def test_load_yaml_config_parses_backup_section(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(
                    """
backup:
  provider: gitlab
  mode: both
  workspace: acme-group
"""
                )

            config = downloader.load_config_file(config_path)

        self.assertEqual("gitlab", config["provider"])
        self.assertEqual("both", config["mode"])
        self.assertEqual("acme-group", config["workspace"])

    @unittest.skipUnless(YAML_AVAILABLE, "PyYAML is required")
    def test_load_yaml_config_with_yml_extension(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write("backup:\n  provider: bitbucket\n")

            config = downloader.load_config_file(config_path)

        self.assertEqual("bitbucket", config["provider"])

    @unittest.skipUnless(TOML_AVAILABLE, "TOML parser is required")
    def test_load_toml_config_without_backup_section_uses_top_level(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(
                    """
provider = "github"
mode = "mirror"
"""
                )

            config = downloader.load_config_file(config_path)

        self.assertEqual("github", config["provider"])
        self.assertEqual("mirror", config["mode"])

    def test_load_config_file_raises_error_for_unsupported_extension(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write("{}")

            with self.assertRaises(ProviderConfigurationError) as ctx:
                downloader.load_config_file(config_path)

            self.assertIn("extension must be", str(ctx.exception))

    @unittest.skipUnless(TOML_AVAILABLE, "TOML parser is required")
    def test_load_toml_config_raises_error_for_invalid_syntax(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write("[invalid toml syntax\n")

            with self.assertRaises(ProviderConfigurationError) as ctx:
                downloader.load_config_file(config_path)

            self.assertIn("Invalid TOML", str(ctx.exception))

    @unittest.skipUnless(YAML_AVAILABLE, "PyYAML is required")
    def test_load_yaml_config_raises_error_for_invalid_syntax(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write("backup:\n  - invalid: [yaml\n")

            with self.assertRaises(ProviderConfigurationError) as ctx:
                downloader.load_config_file(config_path)

            self.assertIn("Invalid YAML", str(ctx.exception))

    def test_load_config_file_raises_error_for_nonexistent_file(self):
        import downloader

        with self.assertRaises(ProviderConfigurationError) as ctx:
            downloader.load_config_file("/nonexistent/config.toml")

        self.assertIn("Failed reading config file", str(ctx.exception))

    @unittest.skipUnless(YAML_AVAILABLE, "PyYAML is required")
    def test_load_yaml_config_handles_empty_file(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write("")

            config = downloader.load_config_file(config_path)

        self.assertEqual({}, config)

    @unittest.skipUnless(TOML_AVAILABLE, "TOML parser is required")
    def test_load_toml_config_with_list_values(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(
                    """
[backup]
include = ["acme/*", "other/*"]
exclude = ["acme/private-*"]
branch = ["main", "dev"]
"""
                )

            config = downloader.load_config_file(config_path)

        self.assertEqual(["acme/*", "other/*"], config["include"])
        self.assertEqual(["acme/private-*"], config["exclude"])
        self.assertEqual(["main", "dev"], config["branch"])

    def test_load_config_file_expands_tilde_in_path(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write("provider = 'bitbucket'\n")

            expanded_path = config_path.replace(os.path.expanduser("~"), "~", 1)
            if expanded_path.startswith("~"):
                config = downloader.load_config_file(expanded_path)
                self.assertEqual("bitbucket", config["provider"])

    @unittest.skipUnless(TOML_AVAILABLE, "TOML parser is required")
    def test_load_config_file_raises_error_for_non_dict_payload(self):
        import downloader

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write("# empty file returns empty dict\n")

            config = downloader.load_config_file(config_path)
            self.assertIsInstance(config, dict)

    def test_apply_config_defaults_does_not_override_cli_arguments(self):
        import argparse
        import downloader

        parser = downloader.build_parser()
        args = parser.parse_args(["--provider", "gitlab", "--mode", "working"])

        configured = downloader.apply_config_defaults(
            parser,
            args,
            {"provider": "bitbucket", "mode": "mirror", "workspace": "acme"},
        )

        self.assertEqual("gitlab", configured.provider)
        self.assertEqual("working", configured.mode)
        self.assertEqual("acme", configured.workspace)

    def test_apply_config_defaults_converts_string_to_list_for_repeatable_keys(self):
        import argparse
        import downloader

        parser = downloader.build_parser()
        args = parser.parse_args([])

        configured = downloader.apply_config_defaults(
            parser,
            args,
            {"include": "acme/*", "exclude": "other/*", "branch": "main"},
        )

        self.assertEqual(["acme/*"], configured.include)
        self.assertEqual(["other/*"], configured.exclude)
        self.assertEqual(["main"], configured.branch)

    def test_apply_config_defaults_keeps_list_values_unchanged(self):
        import argparse
        import downloader

        parser = downloader.build_parser()
        args = parser.parse_args([])

        configured = downloader.apply_config_defaults(
            parser,
            args,
            {"include": ["acme/*", "other/*"], "branch": ["main", "dev"]},
        )

        self.assertEqual(["acme/*", "other/*"], configured.include)
        self.assertEqual(["main", "dev"], configured.branch)

    def test_apply_config_defaults_ignores_unknown_config_keys(self):
        import argparse
        import downloader

        parser = downloader.build_parser()
        args = parser.parse_args([])

        configured = downloader.apply_config_defaults(
            parser,
            args,
            {"provider": "github", "unknown_key": "value"},
        )

        self.assertEqual("github", configured.provider)
        self.assertFalse(hasattr(configured, "unknown_key"))


if __name__ == "__main__":
    unittest.main()