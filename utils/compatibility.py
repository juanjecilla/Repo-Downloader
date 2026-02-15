"""Runtime compatibility helpers for supported environments."""

import re
import subprocess
import sys


SUPPORTED_PLATFORM_KEYS = ("linux", "darwin", "win32")
SUPPORTED_PLATFORM_LABELS = ("linux", "macos", "windows")
MINIMUM_PYTHON_VERSION = (3, 8)
MINIMUM_GIT_VERSION = (2, 30, 0)


def _normalize_version(version_tuple, width=3):
    normalized = list(version_tuple)
    while len(normalized) < width:
        normalized.append(0)
    return tuple(normalized[:width])


def version_tuple_to_text(version_tuple):
    if not version_tuple:
        return "unknown"
    return ".".join(str(part) for part in version_tuple)


def parse_git_version(raw_output):
    if not raw_output:
        return None
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", str(raw_output))
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def detect_git_version():
    try:
        output = subprocess.check_output(  # noqa: S603
            ["git", "--version"],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return output, parse_git_version(output)


def is_python_supported(version_info=None):
    current = tuple((version_info or sys.version_info)[:2])
    return current >= MINIMUM_PYTHON_VERSION


def is_git_supported(version_tuple):
    if not version_tuple:
        return False
    return _normalize_version(version_tuple) >= _normalize_version(MINIMUM_GIT_VERSION)


def is_platform_supported(platform=None):
    current_platform = platform or sys.platform
    return current_platform in SUPPORTED_PLATFORM_KEYS


def build_runtime_compatibility_report(version_info=None, platform=None, git_output=None):
    current_version_info = version_info or sys.version_info
    current_platform = platform or sys.platform

    if git_output is None:
        detected_git_output, git_version = detect_git_version()
    else:
        detected_git_output = str(git_output)
        git_version = parse_git_version(detected_git_output)

    return {
        "python_version": version_tuple_to_text(tuple(current_version_info[:3])),
        "minimum_python_version": version_tuple_to_text(MINIMUM_PYTHON_VERSION),
        "python_supported": is_python_supported(current_version_info),
        "platform": current_platform,
        "supported_platforms": list(SUPPORTED_PLATFORM_LABELS),
        "platform_supported": is_platform_supported(current_platform),
        "git_version_raw": detected_git_output,
        "git_version": version_tuple_to_text(git_version) if git_version else None,
        "minimum_git_version": version_tuple_to_text(MINIMUM_GIT_VERSION),
        "git_supported": is_git_supported(git_version),
    }
