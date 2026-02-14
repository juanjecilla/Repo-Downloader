from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class RemoteProvider(ABC):
    """Contract for remote repository providers."""

    provider_name: str = "unknown"

    @abstractmethod
    def get_user_info(self) -> Optional[Dict]:
        """Return current authenticated user info, if available."""

    @abstractmethod
    def list_repositories(self, workspace: Optional[str] = None, role: str = "member") -> List[Dict]:
        """Return repository records available to the user."""

    @abstractmethod
    def get_repository(self, workspace: str, name: str) -> Optional[Dict]:
        """Return detailed repository information."""

    @abstractmethod
    def list_branches(self, full_name: str) -> List[Dict]:
        """Return branch records for a repository full name."""

    @abstractmethod
    def auth_ok(self) -> bool:
        """Return True if the provider is authenticated and usable."""

    @property
    @abstractmethod
    def auth_error(self) -> Optional[str]:
        """Return an auth/setup error message when available."""
