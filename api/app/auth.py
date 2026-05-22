from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from .config import settings


def verify_api_key(x_api_key: str | None = Header(default=None)) -> str:
    if x_api_key is None or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key
