import hashlib
import hmac
import ipaddress
import secrets

from django.conf import settings


def generate_anonymous_identifier():
    return secrets.token_urlsafe(24)


def generate_write_token():
    return secrets.token_urlsafe(32)


def hash_write_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_write_token(token_hash, raw_token):
    return hmac.compare_digest(token_hash, hash_write_token(raw_token))


def extract_client_ip(request):
    remote_addr = request.META.get("REMOTE_ADDR") or None
    if not remote_addr:
        return None

    trusted_proxies = set(getattr(settings, "TRUSTED_PROXY_IPS", []))
    if remote_addr not in trusted_proxies:
        return remote_addr

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not forwarded_for:
        return remote_addr

    candidate = forwarded_for.split(",")[0].strip()
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return remote_addr
    return candidate
