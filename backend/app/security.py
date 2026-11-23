"""Password hashing (bcrypt, NFR-5.3.4) and JWT tokens."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; truncate explicitly so behaviour is defined.
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user_id: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=s.jwt_expire_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> str | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm]).get("sub")
    except jwt.PyJWTError:
        return None
