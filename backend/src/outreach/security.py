"""
Passwords and session tokens.

Two rules worth stating, because both are easy to get wrong quietly:

  * The password hash is argon2id, and verification failures are caught here
    rather than allowed to escape as library exceptions, so no caller can
    accidentally treat "wrong password" as "server error".

  * The session token lives in an httpOnly cookie, not localStorage. A token
    JavaScript can read is a token any injected script can steal, and this
    application renders text fetched from arbitrary websites.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from outreach.config import settings

log = structlog.get_logger(__name__)

_hasher = PasswordHasher()

ALGORITHM = "HS256"
COOKIE_NAME = "outreach_session"


# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """False for a wrong password, never an exception."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception as exc:  # pragma: no cover
        log.warning("security.verify_failed", error=str(exc))
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than we use now."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return False


# ---------------------------------------------------------------- sessions


def create_session_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(days=settings.session_days),
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def read_session_token(token: str) -> uuid.UUID | None:
    """The user id, or None if the token is missing, expired or tampered with."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# ---------------------------------------------------------- password resets

#: How long a reset link works for.
#:
#: An hour is the usual compromise: long enough to survive a slow mail
#: server and somebody reading their email after lunch, short enough that a
#: link left sitting in an inbox stops being a key to the account.
RESET_TTL = timedelta(hours=1)

#: 32 bytes of randomness, url-safe. Long enough that guessing is not a
#: strategy, which is why this is hashed with sha256 rather than argon2 -
#: there is no dictionary to slow an attacker down through.
_RESET_BYTES = 32


def new_reset_token() -> tuple[str, str]:
    """
    Returns (token, token_hash).

    The token goes in the link and is never stored. The hash is stored and
    never leaves the server, so a copy of the database is not a set of
    skeleton keys to every account in it.
    """
    token = secrets.token_urlsafe(_RESET_BYTES)
    return token, hash_reset_token(token)


def hash_reset_token(token: str) -> str:
    """Plain sha256, so the row can be found *by* the hash."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def reset_expiry() -> datetime:
    return datetime.now(UTC) + RESET_TTL
