"""Safe outbound fetching for URLs that visitors control (their feeds and the pages those feeds link to).

Anyone with a workspace can add a feed URL, so the server must never be tricked into requesting its own
network (localhost, cloud metadata, private ranges). Every hop, including redirects, is checked, and
responses are size-capped. DNS is resolved at check time, so a hostile resolver could still rebind
between the check and the connection; the real mitigation for that is running without access to
internal networks, which Vercel Functions already do.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

ALLOWED_PORTS = {None, 80, 443, 8080, 8443}  # None means the scheme's default port
MAX_REDIRECTS = 4  # hops followed before giving up


class UnsafeURL(ValueError):
    """The URL is not a public http(s) address."""


def check_url(url: str) -> None:
    """Raise UnsafeURL unless `url` is http(s) on a normal port and every address it resolves to is public."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURL("Only public http(s) URLs are allowed")
    try:
        port = parsed.port
    except ValueError:
        raise UnsafeURL("Invalid port") from None
    if port not in ALLOWED_PORTS:
        raise UnsafeURL("That port is not allowed")
    try:
        infos = socket.getaddrinfo(parsed.hostname, port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise UnsafeURL("That host could not be resolved") from None
    # Take each resolved IP from the sockaddr tuple, stripping any IPv6 zone id ("%eth0").
    addresses = {info[4][0].split("%")[0] for info in infos}
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise UnsafeURL("That address is not public")


def fetch(url: str, *, headers: dict | None = None, timeout: float = 12.0, max_bytes: int = 3_000_000) -> httpx.Response:
    """GET `url`, validating the URL and every redirect hop, and reading at most `max_bytes`."""
    # The first request plus up to MAX_REDIRECTS hops, each re-checked before it is requested.
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        with httpx.stream("GET", url, headers=headers, timeout=timeout, follow_redirects=False) as resp:
            if resp.is_redirect and resp.headers.get("location"):
                url = urljoin(url, resp.headers["location"])
                continue
            body = bytearray()
            # Stream the body and stop reading once it passes the size cap.
            for chunk in resp.iter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    break
            return httpx.Response(resp.status_code, headers=resp.headers, content=bytes(body[:max_bytes]),
                                  request=resp.request)
    raise UnsafeURL("Too many redirects")
