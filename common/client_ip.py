import ipaddress

from django.conf import settings


def _parse_ip(value):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _trusted_networks():
    return tuple(ipaddress.ip_network(value, strict=False) for value in settings.TRUSTED_PROXY_IPS)


def get_client_ip(request):
    """Return the address of the client as seen by the outermost trusted proxy.

    X-Forwarded-For is honoured only when the direct peer is a trusted proxy
    (TRUSTED_PROXY_IPS, IPs or CIDR ranges). The header is read right to left,
    skipping trusted hops, because each proxy appends the address it received
    the request from: the left-most entries are whatever the client sent and
    must never be used for rate limiting or audit logs.
    """
    remote_addr = _parse_ip(request.META.get("REMOTE_ADDR") or "")
    if remote_addr is None:
        return None

    trusted = _trusted_networks()

    def is_trusted(address):
        return any(address in network for network in trusted)

    if not is_trusted(remote_addr):
        return str(remote_addr)

    for hop in reversed(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")):
        address = _parse_ip(hop)
        if address is None:
            # A malformed hop means the chain can no longer be trusted.
            break
        if not is_trusted(address):
            return str(address)
    return str(remote_addr)
