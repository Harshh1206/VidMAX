from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from app.core.errors import MetadataUnavailableError
from app.core.urls import NormalizedURL


class MetadataInspector(Protocol):
    async def fetch(self, normalized: NormalizedURL) -> Mapping[str, Any]: ...


class NoopInspector:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def fetch(self, normalized: NormalizedURL) -> Mapping[str, Any]:
        raise MetadataUnavailableError(self.reason, details={"url": normalized.url})


class HttpJsonInspector:
    def __init__(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        *,
        timeout_seconds: float,
        max_bytes: int,
        extra_params: Mapping[str, str] | None = None,
    ) -> None:
        self.client = client
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.extra_params = dict(extra_params or {})

    async def fetch(self, normalized: NormalizedURL) -> Mapping[str, Any]:
        params: dict[str, str] = {
            "url": normalized.url,
            "format": "json",
            **self.extra_params,
        }
        try:
            response = await self.client.get(
                self.endpoint,
                params=params,
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            if len(response.content) > self.max_bytes:
                raise MetadataUnavailableError("Metadata response exceeded the size limit")
            payload = response.json()
        except httpx.HTTPError as exc:
            raise MetadataUnavailableError("Metadata service request failed") from exc
        except ValueError as exc:
            raise MetadataUnavailableError("Metadata service returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise MetadataUnavailableError("Metadata service returned an unexpected payload")
        return payload
