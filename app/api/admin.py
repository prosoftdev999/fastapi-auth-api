from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.rbac import require_permissions
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.admin import (
    AdminUserResponse,
    AdminUserUpdate,
    RoleAssignmentRequest,
    RoleResponse,
)
from app.schemas.pagination import CursorPage, Page
from app.schemas.report import ReportStatusResponse, ReportTaskResponse
from app.services.pagination import (
    CursorPaginationParams,
    OffsetPaginationParams,
    apply_search,
    apply_sort,
    get_cursor_pagination,
    get_offset_pagination,
    paginate_cursor,
    paginate_offset,
)
from app.services.ws_pubsub import publish_to_user
from app.tasks.reports import generate_user_summary_report

router = APIRouter(prefix="/admin", tags=["Admin"])

_USER_SORT_FIELDS = {"id", "email", "created_at", "is_active", "is_verified"}


@router.get(
    "/users",
    response_model=Page[AdminUserResponse],
    dependencies=[Depends(require_permissions("users:read"))],
)
def list_users(
    db: Session = Depends(get_db),
    pagination: OffsetPaginationParams = Depends(get_offset_pagination),
    is_active: bool | None = Query(None, description="Filter by active status"),
) -> Page:
    statement = select(User)

    if is_active is not None:
        statement = statement.where(User.is_active == is_active)

    statement = apply_search(statement, User, pagination, search_fields=["email"])
    statement = apply_sort(statement, User, pagination, _USER_SORT_FIELDS)

    return paginate_offset(db, statement, pagination)


@router.get(
    "/users/feed",
    response_model=CursorPage[AdminUserResponse],
    dependencies=[Depends(require_permissions("users:read"))],
)
def list_users_feed(
    db: Session = Depends(get_db),
    pagination: CursorPaginationParams = Depends(get_cursor_pagination),
) -> CursorPage:
    statement = select(User)

    if pagination.q:
        statement = statement.where(User.email.ilike(f"%{pagination.q}%"))

    try:
        return paginate_cursor(db, statement, User, pagination)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    dependencies=[Depends(require_permissions("users:write"))],
)
def update_user_status(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if payload.is_active is not None:
        user.is_active = payload.is_active

    if payload.is_verified is not None:
        user.is_verified = payload.is_verified

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("users:delete"))],
)
def deactivate_user(user_id: int, db: Session = Depends(get_db)) -> Response:
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user.is_active = False

    db.add(user)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/roles",
    response_model=list[RoleResponse],
    dependencies=[Depends(require_permissions("roles:manage"))],
)
def list_roles(db: Session = Depends(get_db)) -> list[Role]:
    return list(db.scalars(select(Role)))


@router.post(
    "/users/{user_id}/roles",
    response_model=AdminUserResponse,
    dependencies=[Depends(require_permissions("roles:manage"))],
)
async def assign_role(
    user_id: int,
    payload: RoleAssignmentRequest,
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    role = db.scalar(select(Role).where(Role.name == payload.role))

    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )

    if role not in user.roles:
        user.roles.append(role)
        db.add(user)
        db.commit()
        db.refresh(user)

        await publish_to_user(
            user.id,
            {
                "type": "notification",
                "body": f"You have been granted the '{role.name}' role",
            },
        )

    return user


@router.delete(
    "/users/{user_id}/roles/{role_name}",
    response_model=AdminUserResponse,
    dependencies=[Depends(require_permissions("roles:manage"))],
)
def revoke_role(
    user_id: int,
    role_name: str,
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user.roles = [role for role in user.roles if role.name != role_name]

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post(
    "/reports/user-summary",
    response_model=ReportTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("users:read"))],
)
def trigger_user_summary_report() -> ReportTaskResponse:
    """Enqueues report generation on a Celery worker rather than computing
    it inline — poll GET /admin/reports/{task_id} for the result."""
    task = generate_user_summary_report.delay()
    return ReportTaskResponse(task_id=task.id, status=task.status)


@router.get(
    "/reports/{task_id}",
    response_model=ReportStatusResponse,
    dependencies=[Depends(require_permissions("users:read"))],
)
def get_report_status(task_id: str) -> ReportStatusResponse:
    result = AsyncResult(task_id, app=celery_app)

    return ReportStatusResponse(
        task_id=task_id,
        status=result.status,
        result=result.result if result.ready() and result.successful() else None,
    )
