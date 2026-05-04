"""Auth profile storage backed by OS keyring for secrets."""

import json
import os
from datetime import datetime, timezone

from platformdirs import user_config_dir

from utils.errors import ProviderConfigurationError

KEYRING_SERVICE = "repo-downloader"
PROFILE_FILE_NAME = "auth-profiles.json"


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _profile_key(provider, profile):
    return f"{provider}:{profile}"


def _config_dir():
    return user_config_dir("repo-downloader")


def profile_store_path():
    return os.path.join(_config_dir(), PROFILE_FILE_NAME)


def _load_payload(path=None):
    store_path = path or profile_store_path()
    if not os.path.isfile(store_path):
        return {"profiles": {}}

    try:
        with open(store_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, TypeError, ValueError):
        return {"profiles": {}}

    if not isinstance(payload, dict):
        return {"profiles": {}}
    if "profiles" not in payload or not isinstance(payload["profiles"], dict):
        payload["profiles"] = {}
    return payload


def _save_payload(payload, path=None):
    store_path = path or profile_store_path()
    store_dir = os.path.dirname(store_path)
    if store_dir:
        os.makedirs(store_dir, exist_ok=True)

    temp_path = f"{store_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.write("\n")
    os.replace(temp_path, store_path)


def get_auth_profile(provider, profile="default", path=None):
    payload = _load_payload(path=path)
    return payload["profiles"].get(_profile_key(provider, profile))


def set_auth_profile(provider, profile="default", username=None, user_hint=None, path=None):
    payload = _load_payload(path=path)
    key = _profile_key(provider, profile)
    now = _utc_now_iso()

    existing = payload["profiles"].get(key, {})
    created_at = existing.get("created_at", now)
    profile_record = {
        "provider": provider,
        "profile": profile,
        "created_at": created_at,
        "updated_at": now,
        "validated_at": now,
    }
    if username:
        profile_record["username"] = username
    if user_hint:
        profile_record["user_hint"] = user_hint

    payload["profiles"][key] = profile_record
    _save_payload(payload, path=path)
    return profile_record


def delete_auth_profile(provider, profile="default", path=None):
    payload = _load_payload(path=path)
    key = _profile_key(provider, profile)
    existed = key in payload["profiles"]
    if existed:
        del payload["profiles"][key]
        _save_payload(payload, path=path)
    return existed


def _get_keyring_module():
    try:
        import keyring
    except ModuleNotFoundError as exc:
        raise ProviderConfigurationError(
            "Missing dependency 'keyring'. Install project dependencies."
        ) from exc
    return keyring


def get_profile_secret(provider, profile="default"):
    keyring = _get_keyring_module()
    key_name = _profile_key(provider, profile)
    try:
        return keyring.get_password(KEYRING_SERVICE, key_name)
    except (keyring.errors.KeyringError, RuntimeError) as exc:  # pragma: no cover
        raise ProviderConfigurationError(
            "Failed reading credential from keyring. "
            "Ensure a supported keyring backend is available."
        ) from exc


def set_profile_secret(provider, profile="default", secret=None):
    if not secret:
        raise ProviderConfigurationError("Secret value is required for auth profile storage.")

    keyring = _get_keyring_module()
    key_name = _profile_key(provider, profile)
    try:
        keyring.set_password(KEYRING_SERVICE, key_name, secret)
    except (keyring.errors.KeyringError, RuntimeError) as exc:  # pragma: no cover
        raise ProviderConfigurationError(
            "Failed saving credential to keyring. Ensure a supported keyring backend is available."
        ) from exc


def delete_profile_secret(provider, profile="default"):
    keyring = _get_keyring_module()
    key_name = _profile_key(provider, profile)
    try:
        keyring.delete_password(KEYRING_SERVICE, key_name)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
    except (keyring.errors.KeyringError, RuntimeError) as exc:  # pragma: no cover
        raise ProviderConfigurationError("Failed deleting credential from keyring.") from exc
