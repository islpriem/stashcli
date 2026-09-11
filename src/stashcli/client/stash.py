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
from stashcli.models.admin import (
    AllocationReport,
    DrainState,
    Limit,
    UsageReport,
)
from stashcli.models.filesets import (
    Allocations,
    Fileset,
    Filesets,
    Preflight,
    Transfer,
    Transfers,
)
from stashcli.models.topology import Location, Locations, Storage, Storages, WhoAmI

API_PREFIX = "/api/v1"
API_VERSION = "v1"
RETRYABLE_METHODS = frozenset({"GET", "HEAD"})
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def _warm_body(
    source_storage: str,
    source_path: str,
    target_storage: str,
    fileset: str,
    size_bytes: int | None,
    refresh: bool,
    user: str | None,
) -> dict[str, Any]:
    return {
        "kind": "warm",
        "source": {"storage": source_storage, "path": source_path},
        "target": {"storage": target_storage, "fileset": fileset},
        "size_bytes": size_bytes,
        "refresh": refresh,
        "dry_run": False,
        "user": user,
    }


def _limit_path(user: str, storage: str | None) -> str:
    return f"/limits/{user}/{storage}" if storage else f"/limits/{user}"


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

    def filesets(
        self,
        *,
        storage: str | None = None,
        user: str | None = None,
        name: str | None = None,
        kind: str | None = None,
        state: str | None = None,
    ) -> list[Fileset]:
        params = {"storage": storage, "user": user, "name": name, "kind": kind, "state": state}
        return Filesets.model_validate(self._get("/filesets", params)).filesets

    def transfers(
        self,
        *,
        user: str | None = None,
        state: str | None = None,
        kind: str | None = None,
        storage: str | None = None,
        route: str | None = None,
        fileset_id: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Transfers:
        params = {
            "user": user,
            "state": state,
            "kind": kind,
            "storage": storage,
            "route": route,
            "fileset_id": fileset_id,
            "limit": limit,
            "cursor": cursor,
        }
        return Transfers.model_validate(self._get("/transfers", params))

    def transfer(self, transfer_id: int) -> Transfer:
        return Transfer.model_validate(self._get(f"/transfers/{transfer_id}"))

    def cancel(self, transfer_id: int) -> Transfer:
        return Transfer.model_validate(self._request("DELETE", f"/transfers/{transfer_id}"))

    def create_fileset(
        self, *, storage: str, name: str, size_bytes: int, user: str | None = None
    ) -> Fileset:
        body = {"storage": storage, "name": name, "size_bytes": size_bytes, "user": user}
        return Fileset.model_validate(self._post("/filesets", body))

    def resize_fileset(
        self, fileset_id: int, *, size_bytes: int, force: bool = False
    ) -> Fileset:
        return Fileset.model_validate(
            self._request(
                "PATCH",
                f"/filesets/{fileset_id}",
                body={"size_bytes": size_bytes, "force": force},
            )
        )

    def warm(
        self,
        *,
        source_storage: str,
        source_path: str,
        target_storage: str,
        fileset: str,
        size_bytes: int | None = None,
        refresh: bool = False,
        user: str | None = None,
    ) -> Transfer:
        answer = self._post(
            "/transfers",
            _warm_body(
                source_storage, source_path, target_storage, fileset, size_bytes, refresh, user
            ),
        )
        return Transfer.model_validate(answer)

    def warm_preflight(
        self,
        *,
        source_storage: str,
        source_path: str,
        target_storage: str,
        fileset: str,
        size_bytes: int | None = None,
        refresh: bool = False,
        user: str | None = None,
    ) -> Preflight:
        """What the server would do, without doing it."""
        body = _warm_body(
            source_storage, source_path, target_storage, fileset, size_bytes, refresh, user
        )
        return Preflight.model_validate(self._post("/transfers", {**body, "dry_run": True}))

    def flush(
        self,
        *,
        storage: str,
        fileset: str,
        target_storage: str,
        target_path: str,
        keep: bool = False,
        user: str | None = None,
    ) -> Transfer:
        """Write a fileset out to a path on a source storage."""
        body = {
            "kind": "flush",
            "source": {"storage": storage, "fileset": fileset},
            "target": {"storage": target_storage, "path": target_path},
            "keep": keep,
            "user": user,
        }
        return Transfer.model_validate(self._post("/transfers", body))

    def release(
        self, *, storage: str, fileset: str, discard: bool = False, user: str | None = None
    ) -> Transfer:
        """Delete a fileset. The server decides what may be lost without a flush."""
        body: dict[str, Any] = {
            "kind": "release",
            "target": {"storage": storage, "fileset": fileset},
            "user": user,
        }
        if discard:
            body["discard"] = True
        return Transfer.model_validate(self._post("/transfers", body))

    def set_limit(
        self, *, user: str, storage: str | None, allocation_limit_bytes: int
    ) -> Limit:
        """Admin only; the server says so if the caller is not one."""
        return Limit.model_validate(
            self._request(
                "PUT",
                _limit_path(user, storage),
                body={"allocation_limit_bytes": allocation_limit_bytes},
            )
        )

    def clear_limit(self, *, user: str, storage: str | None) -> None:
        self._request("DELETE", _limit_path(user, storage))

    def drain(self, storage: str, *, drained: bool) -> DrainState:
        verb = "drain" if drained else "undrain"
        return DrainState.model_validate(self._post(f"/storages/{storage}/{verb}", {}))

    def usage_report(
        self, *, group_by: str, since: str | None = None, until: str | None = None
    ) -> UsageReport:
        params = {"group_by": group_by, "since": since, "until": until}
        return UsageReport.model_validate(self._get("/reports/usage", params))

    def allocation_report(self) -> AllocationReport:
        return AllocationReport.model_validate(self._get("/reports/allocation"))

    def allocations(self, *, user: str | None = None) -> Allocations:
        return Allocations.model_validate(self._get("/allocations", {"user": user}))

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        given = {key: value for key, value in (params or {}).items() if value is not None}
        return self._request("GET", path, params=given or None)

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        given = {key: value for key, value in body.items() if value is not None}
        return self._request("POST", path, body=given)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        attempts = self._attempts if self.retryable(method) else 1
        failure = TransportError("the request could not be made")
        for attempt in range(1, attempts + 1):
            response: httpx.Response | None = None
            try:
                response = self._client.request(
                    method,
                    f"{API_PREFIX}{path}",
                    params=params,
                    json=body,
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
