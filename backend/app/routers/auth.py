"""FR-4.1.1: register / login / logout. JWT is stored in an httpOnly cookie."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..errors import ApiError, conflict
from ..models import ROLE_INSTRUCTOR, User
from ..schemas import Credentials, LoginOut, UserOut
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=LoginOut, status_code=201)
def register(body: Credentials, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user and user.password_hash:
        raise conflict("An account with this email already exists", "EMAIL_TAKEN")
    if user:  # invited as TA earlier -> claim the account, keep the TA role
        user.password_hash = hash_password(body.password)
    else:
        user = User(email=email, password_hash=hash_password(body.password), role=ROLE_INSTRUCTOR)
        db.add(user)
    db.commit()
    return {"user": user}


@router.post("/login", response_model=LoginOut)
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "Wrong email or password")
    s = get_settings()
    response.set_cookie(
        s.cookie_name, create_token(user.id), max_age=s.jwt_expire_minutes * 60, httponly=True,
        secure=s.cookie_secure, samesite=s.cookie_samesite, path="/",
    )
    return {"user": user}


@router.post("/logout", status_code=204)
def logout(response: Response):
    s = get_settings()
    response.delete_cookie(s.cookie_name, path="/", secure=s.cookie_secure, samesite=s.cookie_samesite)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
