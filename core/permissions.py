"""Permission checks. Code checks permissions, never role names."""

from fastapi import Depends

from config import roles as role_config
from core.auth import User, get_current_user

AUDIT_VIEW = "core:audit.view"


class PermissionDenied(Exception):
    """Raised when a user lacks a permission. main.py turns it into a 403."""


def effective_permissions(user: User) -> set[str]:
    perms: set[str] = set()
    for role in user.role_names:
        perms.update(role_config.ROLES.get(role, []))
    return perms


def has_permission(user: User, permission: str) -> bool:
    return permission in effective_permissions(user)


def require_permission(permission: str):
    """FastAPI dependency: returns the current user, or denies with 403."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise PermissionDenied(permission)
        return user

    return dependency
