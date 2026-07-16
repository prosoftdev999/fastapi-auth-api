from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.password import hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import PasswordChange, UserResponse, UserUpdate

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
        normalized_email = str(user_data.email).lower()

        existing_user = db.scalar(
            select(User).where(
                User.email == normalized_email,
                User.id != current_user.id,
            )
        )

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )

        current_user.email = normalized_email

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

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
    if not verify_password(
        password_data.current_password,
        current_user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if verify_password(
        password_data.new_password,
        current_user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different",
        )

    current_user.hashed_password = hash_password(
        password_data.new_password
    )

    db.add(current_user)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    current_user.is_active = False

    db.add(current_user)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)