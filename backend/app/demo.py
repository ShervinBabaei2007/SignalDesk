"""Demo mode: short-lived signed tokens that let visitors run ingests without the real API token."""

import hashlib
import hmac
import time

_PREFIX = "demo"  # first segment of every demo token: "demo.<expiry unix time>.<signature>"


def _sign(secret: str, payload: str) -> str:
    """Sign a payload with a key derived from the API token, so a demo token can never be the real one."""
    return hmac.new(f"{secret}:demo".encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue(secret: str, ttl_seconds: int, now: float | None = None) -> str:
    """Create a demo token that expires `ttl_seconds` from now."""
    payload = f"{_PREFIX}.{int((now if now is not None else time.time()) + ttl_seconds)}"
    return f"{payload}.{_sign(secret, payload)}"


def is_valid(token: str, secret: str, now: float | None = None) -> bool:
    """True when the token was signed with this secret and has not expired."""
    parts = token.split(".")
    # Reject anything not shaped like "demo.<digits>.<signature>" before checking the signature.
    if len(parts) != 3 or parts[0] != _PREFIX or not parts[1].isdigit():
        return False
    signature_ok = hmac.compare_digest(parts[2], _sign(secret, f"{parts[0]}.{parts[1]}"))
    return signature_ok and int(parts[1]) > (now if now is not None else time.time())
