import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 30
# A random process-local fallback keeps local development usable without storing a secret.
# Production deployments must set REFLEX_JWT_SECRET to a stable secret.
JWT_SECRET = os.getenv("REFLEX_JWT_SECRET") or secrets.token_urlsafe(32)


def create_access_token(user_id: int, role: str, expires_delta: timedelta | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES)
    )
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "role": role,
        "exp": expires_at,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)