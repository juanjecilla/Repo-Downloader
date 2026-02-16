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


if __name__ == "__main__":
    unittest.main()
