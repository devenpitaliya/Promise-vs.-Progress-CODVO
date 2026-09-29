import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from app.config import settings


def get_password_hash(password: str) -> str:
    """Bcrypt hash. Bcrypt reads at most 72 bytes; the schema caps passwords below that."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode({"sub": subject, "exp": expire, "iat": now}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def _fernet() -> Fernet:
    # Derive a stable Fernet key from SECRET_KEY so user-supplied API keys are encrypted at rest.
    digest = hashlib.sha256(f"api-key-encryption:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # SECRET_KEY was rotated: the stored key is unreadable, so treat it as absent.
        return None


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return "••••••••" if len(value) <= 10 else f"{value[:4]}••••••••{value[-4:]}"
