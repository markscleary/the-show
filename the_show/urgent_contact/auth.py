from __future__ import annotations

import hashlib
import hmac
import random
import string


def get_show_secret(show_id: str) -> str:
    """Derive a deterministic per-show secret for HMAC signing."""
    return hashlib.sha256(f"the-show-secret-v1:{show_id}".encode()).hexdigest()


def generate_reply_token() -> str:
    """Generate a 6-digit numeric reply token."""
    return "".join(random.choices(string.digits, k=6))


def generate_signed_token(show_id: str, matter_id: int, nonce: str) -> str:
    """Generate an HMAC-signed token for signed-link auth."""
    secret = get_show_secret(show_id)
    msg = f"{matter_id}:{nonce}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
    nonce_short = nonce[:8]
    return f"{matter_id}-{nonce_short}-{sig}"


def verify_signed_token(token: str, show_id: str) -> bool:
    """Verify that a signed token was produced by this show's secret."""
    try:
        parts = token.split("-")
        if len(parts) < 3:
            return False
        matter_id_str = parts[0]
        nonce_short = parts[1]
        received_sig = parts[2]
        matter_id = int(matter_id_str)
        # Reconstruct sig from the stored parts — since nonce_short is first 8 chars of nonce,
        # we re-derive using the same input format
        secret = get_show_secret(show_id)
        msg = f"{matter_id}:{nonce_short}".encode()
        expected_sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(received_sig, expected_sig)
    except (ValueError, IndexError):
        return False


def token_in_text(token: str, text: str) -> bool:
    """Return True if token appears anywhere in text (case-insensitive for the rest, exact for token)."""
    return token in text
