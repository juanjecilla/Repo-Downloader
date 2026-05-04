import tempfile
import unittest
from unittest.mock import patch

from utils import auth_store


class _FakeKeyringErrors:
    class KeyringError(Exception):
        pass

    class PasswordDeleteError(KeyringError):
        pass


class _FakeKeyring:
    errors = _FakeKeyringErrors

    def __init__(self):
        self.values = {}

    def get_password(self, service, key):
        return self.values.get((service, key))

    def set_password(self, service, key, secret):
        self.values[(service, key)] = secret

    def delete_password(self, service, key):
        record_key = (service, key)
        if record_key not in self.values:
            raise self.errors.PasswordDeleteError("missing")
        del self.values[record_key]


class TestAuthStore(unittest.TestCase):
    def test_set_get_delete_auth_profile(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            profile_path = f"{tmp_dir}/auth-profiles.json"
            saved = auth_store.set_auth_profile(
                provider="github",
                profile="default",
                username="octocat",
                user_hint="octocat",
                path=profile_path,
            )
            self.assertEqual("github", saved["provider"])
            loaded = auth_store.get_auth_profile("github", "default", path=profile_path)
            self.assertEqual("octocat", loaded["username"])

            deleted = auth_store.delete_auth_profile("github", "default", path=profile_path)
            self.assertTrue(deleted)
            missing = auth_store.get_auth_profile("github", "default", path=profile_path)
            self.assertIsNone(missing)

    def test_secret_round_trip_uses_keyring(self):
        fake_keyring = _FakeKeyring()
        with patch("utils.auth_store._get_keyring_module", return_value=fake_keyring):
            auth_store.set_profile_secret("github", "default", "secret-token")
            token = auth_store.get_profile_secret("github", "default")
            self.assertEqual("secret-token", token)

            deleted = auth_store.delete_profile_secret("github", "default")
            self.assertTrue(deleted)
            self.assertIsNone(auth_store.get_profile_secret("github", "default"))

    def test_delete_profile_secret_returns_false_when_missing(self):
        fake_keyring = _FakeKeyring()
        with patch("utils.auth_store._get_keyring_module", return_value=fake_keyring):
            deleted = auth_store.delete_profile_secret("github", "default")
            self.assertFalse(deleted)

    def test_set_auth_profile_without_username_or_hint(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = f"{tmp_dir}/profiles.json"
            record = auth_store.set_auth_profile("bitbucket", path=path)
            self.assertNotIn("username", record)
            self.assertNotIn("user_hint", record)

    def test_delete_auth_profile_returns_false_for_nonexistent_key(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = f"{tmp_dir}/profiles.json"
            result = auth_store.delete_auth_profile("github", "missing", path=path)
            self.assertFalse(result)

    def test_load_payload_handles_corrupted_json(self):
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            path = f.name
        try:
            payload = auth_store._load_payload(path=path)  # noqa: SLF001
            self.assertEqual({"profiles": {}}, payload)
        finally:
            os.unlink(path)

    def test_load_payload_handles_non_dict_json(self):
        import json
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([1, 2, 3], f)
            path = f.name
        try:
            payload = auth_store._load_payload(path=path)  # noqa: SLF001
            self.assertEqual({"profiles": {}}, payload)
        finally:
            os.unlink(path)

    def test_load_payload_handles_missing_profiles_key(self):
        import json
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"other": "data"}, f)
            path = f.name
        try:
            payload = auth_store._load_payload(path=path)  # noqa: SLF001
            self.assertIn("profiles", payload)
            self.assertIsInstance(payload["profiles"], dict)
        finally:
            os.unlink(path)

    def test_profile_store_path_returns_string(self):
        path = auth_store.profile_store_path()
        self.assertIsInstance(path, str)
        self.assertTrue(path.endswith("auth-profiles.json"))

    def test_get_keyring_module_raises_when_not_installed(self):
        import sys

        from utils.errors import ProviderConfigurationError

        with patch.dict(sys.modules, {"keyring": None}):
            with self.assertRaises(ProviderConfigurationError):
                auth_store._get_keyring_module()  # noqa: SLF001

    def test_set_profile_secret_raises_for_empty_secret(self):
        from utils.errors import ProviderConfigurationError

        with self.assertRaises(ProviderConfigurationError):
            auth_store.set_profile_secret("github", "default", secret="")


if __name__ == "__main__":
    unittest.main()
