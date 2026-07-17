from fastapi import APIRouter, Depends, Response, status

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import PasswordChange, UserResponse, UserUpdate
from app.services.user_profile import (
    change_user_password,
    deactivate_user,
    update_user_email,
)
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/me",
    response_model=UserResponse,
)
def read_current_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
)
def update_current_user(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if user_data.email is not None:
        return update_user_email(db, current_user, str(user_data.email))

    return current_user


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
