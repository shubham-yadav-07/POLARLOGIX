from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import User
from ..security import current_user, decode_token, make_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    username: str
    password: str


class Refresh(BaseModel):
    refresh_token: str


def _user(u: User) -> dict:
    return {"username": u.username, "full_name": u.full_name, "role": u.role, "station": u.station}


@router.post("/login")
def login(body: Login, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == body.username.strip().lower()).first()
    if u is None or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong username or password")
    audit(db, u.username, "login", "user", u.username)
    db.commit()
    return {"access_token": make_token(u), "refresh_token": make_token(u, "refresh"), "user": _user(u)}


@router.post("/refresh")
def refresh(body: Refresh, db: Session = Depends(get_db)):
    data = decode_token(body.refresh_token, "refresh")
    u = db.query(User).filter(User.username == data["sub"]).first()
    if u is None:
        raise HTTPException(401, "Unknown user")
    return {"access_token": make_token(u), "refresh_token": make_token(u, "refresh"), "user": _user(u)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _user(user)
