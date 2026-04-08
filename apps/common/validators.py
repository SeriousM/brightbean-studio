"""Shared validation utilities."""

import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_url(url: str) -> bool:
    """Validate that a URL does not resolve to a private/reserved IP (SSRF protection).

    Returns False for URLs that resolve to private, reserved, loopback, or
    link-local IP addresses to prevent server-side request forgery.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        for family, _, _, _, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                return False

        return True
    except (socket.gaierror, ValueError, OSError):
        return False
