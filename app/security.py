"""Password hashing (bcrypt), JWT access + refresh tokens, role-based access."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

ALGO = "HS256"
bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt(rounds=10)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def make_token(user: User, kind: str = "access") -> str:
    delta = timedelta(minutes=settings.access_token_minutes) if kind == "access" else timedelta(days=settings.refresh_token_days)
    payload = {"sub": user.username, "role": user.role, "kind": kind, "exp": datetime.now(timezone.utc) + delta}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGO)


def decode_token(token: str, kind: str = "access") -> dict:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if data.get("kind") != kind:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    return data


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    data = decode_token(cred.credentials)
    user = db.query(User).filter(User.username == data["sub"]).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{user.role}' cannot do this")
        return user
    return dep


ALL = ("manager", "leader", "field", "logistics")
OPS = ("manager", "leader")
