import unittest

from utils import compatibility


class TestCompatibility(unittest.TestCase):
    def test_parse_git_version_with_patch(self):
        parsed = compatibility.parse_git_version("git version 2.39.3")
        self.assertEqual((2, 39, 3), parsed)

    def test_parse_git_version_without_patch(self):
        parsed = compatibility.parse_git_version("git version 2.30")
        self.assertEqual((2, 30, 0), parsed)

    def test_parse_git_version_unknown_output(self):
        parsed = compatibility.parse_git_version("git version unknown")
        self.assertIsNone(parsed)

    def test_build_runtime_report_supported_inputs(self):
        report = compatibility.build_runtime_compatibility_report(
            version_info=(3, 11, 8, "final", 0),
            platform="linux",
            git_output="git version 2.44.0",
        )
        self.assertTrue(report["python_supported"])
        self.assertTrue(report["platform_supported"])
        self.assertTrue(report["git_supported"])
        self.assertEqual("3.11.8", report["python_version"])
        self.assertEqual("2.44.0", report["git_version"])

    def test_build_runtime_report_unsupported_inputs(self):
        report = compatibility.build_runtime_compatibility_report(
            version_info=(3, 7, 9, "final", 0),
            platform="freebsd",
            git_output="git version 2.18.0",
        )
        self.assertFalse(report["python_supported"])
        self.assertFalse(report["platform_supported"])
        self.assertFalse(report["git_supported"])
        self.assertEqual("3.7.9", report["python_version"])
        self.assertEqual("2.18.0", report["git_version"])

    def test_version_tuple_to_text_for_empty_values(self):
        self.assertEqual("unknown", compatibility.version_tuple_to_text(None))
        self.assertEqual("unknown", compatibility.version_tuple_to_text(()))


if __name__ == "__main__":
    unittest.main()
