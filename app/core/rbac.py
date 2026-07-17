from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.models.role import Permission, Role
from app.models.user import User

DEFAULT_PERMISSIONS: dict[str, str] = {
    "users:read": "View any user's account",
    "users:write": "Update any user's account",
    "users:delete": "Deactivate any user's account",
    "roles:manage": "Assign or revoke roles",
}

DEFAULT_ROLES: dict[str, str] = {
    "admin": "Full administrative access",
    "moderator": "Can view and moderate user accounts",
    "user": "Standard authenticated user",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"users:read", "users:write", "users:delete", "roles:manage"},
    "moderator": {"users:read", "users:write"},
    "user": set(),
}

DEFAULT_USER_ROLE_NAME = "user"


class RoleChecker:
    """Depends(RoleChecker("admin", "moderator")) — allow any of the given roles."""

    def __init__(self, *allowed_roles: str) -> None:
        self.allowed_roles = set(allowed_roles)

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_role_names = {role.name for role in current_user.roles}

        if not user_role_names & self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have the required role for this action",
            )

        return current_user


class PermissionChecker:
    """Depends(PermissionChecker("users:write")) — require all given permissions."""

    def __init__(self, *required_permissions: str) -> None:
        self.required_permissions = set(required_permissions)

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_permissions = {
            permission.name
            for role in current_user.roles
            for permission in role.permissions
        }

        if not self.required_permissions <= user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have the required permission for this action",
            )

        return current_user


def require_roles(*roles: str) -> RoleChecker:
    return RoleChecker(*roles)


def require_permissions(*permissions: str) -> PermissionChecker:
    return PermissionChecker(*permissions)


def seed_rbac_defaults(session: Session) -> None:
    """Idempotently ensure the default roles/permissions exist.

    Used by the RBAC Alembic migration's data-seed step and by the test
    suite (which builds its schema via Base.metadata.create_all rather than
    running migrations).
    """
    permissions_by_name: dict[str, Permission] = {}

    for name, description in DEFAULT_PERMISSIONS.items():
        permission = session.scalar(
            select(Permission).where(Permission.name == name)
        )
        if permission is None:
            permission = Permission(name=name, description=description)
            session.add(permission)
            session.flush()
        permissions_by_name[name] = permission

    for role_name, description in DEFAULT_ROLES.items():
        role = session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name, description=description)
            session.add(role)
            session.flush()

        wanted = ROLE_PERMISSIONS.get(role_name, set())
        current = {permission.name for permission in role.permissions}

        for permission_name in wanted - current:
            role.permissions.append(permissions_by_name[permission_name])

    session.commit()
