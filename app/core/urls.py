import ipaddress
import re
from dataclasses import dataclass, replace
from urllib.parse import urlsplit, urlunsplit

from app.core.errors import InvalidURLError, UnsupportedPlatformError

_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_BLOCKED_SUFFIXES = (
    ".local",
    ".localhost",
    ".localdomain",
    ".internal",
    ".test",
    ".invalid",
    ".example",
    ".home.arpa",
)
_BLOCKED_HOSTS = frozenset({"localhost", "localhost.localdomain"})


@dataclass(frozen=True)
class NormalizedURL:
    url: str
    host: str
    scheme: str
    path: str
    query: str
    resource_id: str | None = None


class URLGuard:
    def parse(self, url: str) -> NormalizedURL:
        if not isinstance(url, str) or not url or len(url) > 2048:
            raise InvalidURLError("The URL must be a non-empty string of at most 2048 characters")
        if any(char.isspace() or ord(char) < 32 for char in url):
            raise InvalidURLError("The URL contains whitespace or control characters")

        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise InvalidURLError("The URL could not be parsed") from exc

        if parts.scheme.lower() != "https":
            raise InvalidURLError("Only https URLs are allowed")
        if "@" in parts.netloc or parts.username is not None or parts.password is not None:
            raise InvalidURLError("Credentials in URLs are not allowed")
        try:
            if parts.port is not None:
                raise InvalidURLError("Explicit ports are not allowed")
        except ValueError as exc:
            raise InvalidURLError("The URL port is invalid") from exc

        host = (parts.hostname or "").lower()
        if not host:
            raise InvalidURLError("The URL has no host")
        if host.endswith("."):
            raise InvalidURLError("Trailing-dot hosts are not allowed")
        if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
            raise InvalidURLError("Local hosts are not allowed")
        if host.endswith(_BLOCKED_SUFFIXES):
            raise InvalidURLError("Reserved host suffixes are not allowed")
        if self._is_ip_literal(host):
            raise InvalidURLError("IP address hosts are not allowed")

        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise InvalidURLError("The host could not be normalized") from exc
        if ascii_host != host or not all(_HOST_LABEL_RE.fullmatch(label) for label in host.split(".")):
            raise InvalidURLError("The host contains disallowed characters")

        path = parts.path or "/"
        canonical = urlunsplit(("https", host, path, parts.query, ""))
        return NormalizedURL(url=canonical, host=host, scheme="https", path=path, query=parts.query)

    def validate_candidate(self, url: str, allowed_hosts: frozenset[str] | set[str]) -> NormalizedURL:
        normalized = self.parse(url)
        allowed = {host.lower() for host in allowed_hosts}
        if normalized.host not in allowed:
            raise UnsupportedPlatformError(f"Host {normalized.host!r} is not allowed")
        return normalized

    def with_resource_id(self, normalized: NormalizedURL, resource_id: str) -> NormalizedURL:
        return replace(normalized, resource_id=resource_id)

    def validate_redirect(
        self,
        location: str,
        allowed_hosts: frozenset[str] | set[str],
    ) -> NormalizedURL:
        return self.validate_candidate(location, allowed_hosts)

    def validate_redirect_chain(
        self,
        locations: list[str],
        allowed_hosts: frozenset[str] | set[str],
        max_redirects: int = 5,
    ) -> NormalizedURL | None:
        if not locations:
            return None
        if len(locations) > max_redirects:
            raise InvalidURLError("Too many redirects")
        final = None
        for location in locations:
            final = self.validate_redirect(location, allowed_hosts)
        return final

    @staticmethod
    def _is_ip_literal(host: str) -> bool:
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False
