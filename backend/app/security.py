from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_jwt_secret
from .db import get_session
from .models import Host

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(days=7)

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(host_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(host_id), "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def host_for_token(token: str, session: Session) -> Host | None:
    """The host a JWT belongs to, or None if it's invalid, expired or the host is gone."""
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        host_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
    return session.get(Host, host_id)


def get_current_host(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> Host:
    host = host_for_token(creds.credentials, session) if creds else None
    if host is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return host
