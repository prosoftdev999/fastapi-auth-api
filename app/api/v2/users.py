from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.schemas.user import PasswordChange, UserUpdate
from app.schemas.user_v2 import UserResponseV2
from app.services.user_profile import (
    change_user_password,
    deactivate_user,
    update_user_email,
)

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/me",
    response_model=UserResponseV2,
)
def read_current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponseV2:
    linked_providers = list(
        db.scalars(
            select(OAuthAccount).where(OAuthAccount.user_id == current_user.id)
        )
    )

    return UserResponseV2(
        id=current_user.id,
        email=current_user.email,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        roles=current_user.roles,
        oauth_providers=linked_providers,
    )


@router.patch(
    "/me",
    response_model=UserResponseV2,
)
def update_current_user(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponseV2:
    if user_data.email is not None:
        update_user_email(db, current_user, str(user_data.email))

    return read_current_user(current_user=current_user, db=db)


@router.post(
    "/me/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def change_current_user_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    change_user_password(
        db,
        current_user,
        password_data.current_password,
        password_data.new_password,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    deactivate_user(db, current_user)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
