"""add RBAC tables (roles, permissions) and seed defaults

Revision ID: 49f933ee3842
Revises: 6fe368ffba4d
Create Date: 2026-07-16

Note: the seed data below is intentionally duplicated from
app.core.rbac.DEFAULT_ROLES/DEFAULT_PERMISSIONS/ROLE_PERMISSIONS rather than
importing it. Migrations are historical snapshots — if those constants
change later, this migration must keep inserting exactly what it always
did, or replaying it from scratch would produce different data than the
day it was written.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "49f933ee3842"
down_revision: Union[str, Sequence[str], None] = "6fe368ffba4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERMISSIONS = [
    ("users:read", "View any user's account"),
    ("users:write", "Update any user's account"),
    ("users:delete", "Deactivate any user's account"),
    ("roles:manage", "Assign or revoke roles"),
]

ROLES = [
    ("admin", "Full administrative access"),
    ("moderator", "Can view and moderate user accounts"),
    ("user", "Standard authenticated user"),
]

ROLE_PERMISSIONS = {
    "admin": {"users:read", "users:write", "users:delete", "roles:manage"},
    "moderator": {"users:read", "users:write"},
    "user": set(),
}


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=32), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            sa.Integer(),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    bind = op.get_bind()

    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
    )
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
    )
    user_roles_table = sa.table(
        "user_roles",
        sa.column("user_id", sa.Integer),
        sa.column("role_id", sa.Integer),
    )

    permission_ids: dict[str, int] = {}
    for name, description in PERMISSIONS:
        result = bind.execute(
            permissions_table.insert()
            .values(name=name, description=description)
            .returning(permissions_table.c.id)
        )
        permission_ids[name] = result.scalar_one()

    role_ids: dict[str, int] = {}
    for name, description in ROLES:
        result = bind.execute(
            roles_table.insert()
            .values(name=name, description=description)
            .returning(roles_table.c.id)
        )
        role_ids[name] = result.scalar_one()

    for role_name, permission_names in ROLE_PERMISSIONS.items():
        for permission_name in permission_names:
            bind.execute(
                role_permissions_table.insert().values(
                    role_id=role_ids[role_name],
                    permission_id=permission_ids[permission_name],
                )
            )

    # Grant every pre-existing user the default "user" role.
    users_table = sa.table("users", sa.column("id", sa.Integer))
    existing_user_ids = [row[0] for row in bind.execute(sa.select(users_table.c.id))]
    for user_id in existing_user_ids:
        bind.execute(
            user_roles_table.insert().values(
                user_id=user_id, role_id=role_ids["user"]
            )
        )


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
