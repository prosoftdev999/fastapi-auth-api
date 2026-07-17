from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.password import hash_password, verify_password
from app.models.user import User

# Extracted out of app/api/users.py so both the v1 and v2 routers can share
# it without duplicating the logic — routers stay thin, this is where the
# actual business rules live.


def update_user_email(db: Session, user: User, new_email: str) -> User:
    normalized_email = new_email.lower()

    existing_user = db.scalar(
        select(User).where(
            User.email == normalized_email,
            User.id != user.id,
        )
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user.email = normalized_email

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def change_user_password(
    db: Session, user: User, current_password: str, new_password: str
) -> None:
    if user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This account has no password set. "
                "Use the password reset flow to set one."
            ),
        )

    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if verify_password(new_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different",
        )

    user.hashed_password = hash_password(new_password)

    db.add(user)
    db.commit()


def deactivate_user(db: Session, user: User) -> None:
    user.is_active = False

    db.add(user)
    db.commit()
