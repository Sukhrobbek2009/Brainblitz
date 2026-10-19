from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_session
from .models import Host
from .security import create_token, get_current_host, hash_password, verify_password

router = APIRouter()


class Credentials(BaseModel):
    email: EmailStr
    # bcrypt only uses the first 72 bytes; cap length so none is silently ignored
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


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
    if host is None or not verify_password(body.password, host.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"access_token": create_token(host.id), "token_type": "bearer"}


@router.get("/me")
def me(host: Host = Depends(get_current_host)):
    return {"id": host.id, "email": host.email}
