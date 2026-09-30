import hashlib
import hmac
import secrets


def generate_anonymous_identifier():
    return secrets.token_urlsafe(24)


def generate_write_token():
    return secrets.token_urlsafe(32)


def hash_write_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_write_token(token_hash, raw_token):
    return hmac.compare_digest(token_hash, hash_write_token(raw_token))
