# app/utils/token.py

import secrets
import hashlib

def generate_reset_token() -> tuple[str, str]:
    """Returns (raw_token, hashed_token). Raw token goes in email link, hash goes in DB."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash

def hash_token(raw_token: str) -> str:
    """Used to look up a token by hashing what the user submits."""
    return hashlib.sha256(raw_token.encode()).hexdigest()