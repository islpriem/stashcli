"""The typed HTTP client. One method per endpoint, no logic, no formatting.

Only idempotent GETs are retried, and each attempt gets its own MUNGE credential: they are
single-use.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx

from stashcli import __version__
from stashcli.auth.provider import AuthProvider
from stashcli.errors import CliError, ServerError, TransportError
from stashcli.models.topology import Location, Locations, Storage, Storages, WhoAmI

API_PREFIX = "/api/v1"
API_VERSION = "v1"
RETRYABLE_METHODS = frozenset({"GET", "HEAD"})
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def _ignore_warning(message: str) -> None:
    """A library caller that does not want warnings simply gets none."""


def _is_envelope(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and isinstance(payload.get("error"), dict)


class StashClient:
    def __init__(
        self,
        server: str,
        auth: AuthProvider,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        attempts: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
        on_warning: Callable[[str], None] = _ignore_warning,
    ) -> None:
        self._auth = auth
        self._attempts = attempts
        self._sleep = sleeper
        self._warn = on_warning
        self._warned = False
        self._client = httpx.Client(base_url=server, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "StashClient":
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    def retryable(self, method: str) -> bool:
        """A retried POST would submit twice; only idempotent reads are repeated."""
        return method.upper() in RETRYABLE_METHODS

    def whoami(self) -> WhoAmI:
        return WhoAmI.model_validate(self._get("/whoami"))

    def locations(self) -> list[Location]:
        return Locations.model_validate(self._get("/locations")).locations

    def storages(self) -> list[Storage]:
        return Storages.model_validate(self._get("/storages")).storages

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
        attempts = self._attempts if self.retryable(method) else 1
        failure = TransportError("the request could not be made")
        for attempt in range(1, attempts + 1):
            response: httpx.Response | None = None
            try:
                response = self._client.request(
                    method,
                    f"{API_PREFIX}{path}",
                    params=params,
                    headers={"Authorization": f"{self._auth.scheme} {self._auth.credential()}"},
                )
            except httpx.HTTPError as error:
                failure = TransportError(f"cannot reach the STASH server: {error}")
            else:
                self._check_versions(response)
                # A body with an error envelope is an answer, not a hiccup: never retry it.
                if response.status_code not in RETRYABLE_STATUS or _is_envelope(response):
                    return self._body(response)
                failure = TransportError(
                    f"the STASH server answered {response.status_code}",
                    hint="it may be restarting or overloaded; try again",
                )
            if attempt < attempts:
                self._sleep(self._backoff(attempt, response))
        raise failure

    def _backoff(self, attempt: int, response: httpx.Response | None) -> float:
        """Exponential, unless the server said when to come back."""
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return float(2**attempt)

    def _check_versions(self, response: httpx.Response) -> None:
        api = response.headers.get("X-Stash-Api-Version")
        if api is not None and api != API_VERSION:
            raise CliError(
                f"this client speaks API {API_VERSION}, the server speaks {api}",
                hint="install the stashcli that belongs to this server",
            )
        server = response.headers.get("X-Stash-Server-Version")
        if server is not None and server != __version__ and not self._warned:
            self._warned = True
            self._warn(f"server version {server} differs from this client ({__version__})")

    def _body(self, response: httpx.Response) -> Any:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.is_success:
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            error = payload["error"]
            raise ServerError(
                code=str(error.get("code", "INTERNAL")),
                message=str(error.get("message", "the server refused the request")),
                details=dict(error.get("details") or {}),
            )
        raise CliError(
            f"the STASH server answered {response.status_code} without an error body"
        )
