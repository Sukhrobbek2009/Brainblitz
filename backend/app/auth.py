from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_session
from .models import Host
from .security import DUMMY_HASH, create_token, get_current_host, hash_password, verify_password

router = APIRouter()


def _within_bcrypt_limit(v: str) -> str:
    # bcrypt only uses the first 72 *bytes* (not characters), and refuses longer input
    if len(v.encode()) > 72:
        raise ValueError("Password is too long (at most 72 bytes; some characters take more than one).")
    return v


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    _bytes = field_validator("password")(_within_bcrypt_limit)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(max_length=72)
    _bytes = field_validator("password")(_within_bcrypt_limit)


@router.post("/signup", status_code=201)
def signup(body: Credentials, session: Session = Depends(get_session)):
    email = body.email.lower()
    if session.scalar(select(Host).where(Host.email == email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    host = Host(email=email, password_hash=hash_password(body.password))
    session.add(host)
    try:
        session.commit()
    except IntegrityError:  # concurrent signup with the same email
        session.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")
    return {"id": host.id, "email": host.email}


@router.post("/login")
def login(body: LoginRequest, session: Session = Depends(get_session)):
    host = session.scalar(select(Host).where(Host.email == body.email.lower()))
    # always do one bcrypt check, so an unknown email costs the same time as a wrong password
    ok = verify_password(body.password, host.password_hash if host else DUMMY_HASH)
    if host is None or not ok:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"access_token": create_token(host.id), "token_type": "bearer"}


@router.get("/me")
def me(host: Host = Depends(get_current_host)):
    return {"id": host.id, "email": host.email}
