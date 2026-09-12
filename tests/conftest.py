"""A runtime whose client speaks to a MockTransport instead of the network."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from stashcli import __version__
from stashcli.auth.fake import FakeAuthProvider
from stashcli.client.stash import StashClient
from stashcli.config.settings import Settings
from stashcli.render.output import OutputOptions
from stashcli.runtime import Runtime

SERVER = "http://controller:8000"
HEADERS = {"X-Stash-Api-Version": "v1", "X-Stash-Server-Version": __version__}

WHOAMI = {
    "uid": 1000,
    "username": "mmustermann",
    "groups": ["users", "hpc-admin"],
    "admin": False,
    "server_version": __version__,
    "api_version": "v1",
}
LOCATIONS: dict[str, Any] = {
    "locations": [
        {"id": "LOC1", "name": "Site 1", "enabled": True},
        {"id": "LOC2", "name": "Site 2", "enabled": False},
    ]
}
STORAGES: dict[str, Any] = {
    "storages": [
        {
            "id": "HOT1",
            "location": "LOC1",
            "roles": ["source"],
            "tier": "hot",
            "driver": "posix",
            "fileset_prefix": "/gpfs/hot1",
            "capacity_bytes": None,
            "fill_limit": 0.95,
            "default_user_allocation_limit_bytes": None,
            "daemon": "hot1",
            "drained": False,
            "enabled": True,
            "quota_enforced": False,
            "daemon_seen_at": None,
            "daemon_config_revision": None,
        },
        {
            "id": "LOC2HOT",
            "location": "LOC2",
            "roles": ["cache", "source"],
            "tier": "hot",
            "driver": "posix",
            "fileset_prefix": "/cache/loc2",
            "capacity_bytes": 500 * 1024**4,
            "fill_limit": 0.95,
            "default_user_allocation_limit_bytes": 100 * 1024**3,
            "daemon": "loc2hot",
            "drained": True,
            "enabled": True,
            "quota_enforced": False,
            "daemon_seen_at": "2026-09-01T12:00:00Z",
            "daemon_config_revision": 42,
        },
    ]
}

GIB = 1024**3

FILESETS: dict[str, Any] = {
    "filesets": [
        {
            "id": 1,
            "name": "abc",
            "reference": "LOC2HOT:abc",
            "owner_user": "mmustermann",
            "storage_id": "LOC2HOT",
            "kind": "cached",
            "state": "READY",
            "path": "/cache/loc2/mmustermann/abc",
            "allocated_bytes": 39514044170,
            "used_bytes": 37580963840,
            "used_bytes_at": "2026-08-29T09:20:00Z",
            "file_count": 12043,
            "over_allocation": False,
            "source": "HOT1:/myuser/abc",
            "created_at": "2026-08-29T07:00:00Z",
            "warm_started_at": "2026-08-29T07:02:00Z",
            "warm_finished_at": "2026-08-29T09:14:00Z",
            "last_flushed_at": None,
            "last_flush_target": None,
            "released_at": None,
            "last_transfer_id": 123456,
        },
        {
            "id": 2,
            "name": "results",
            "reference": "LOC2HOT:results",
            "owner_user": "mmustermann",
            "storage_id": "LOC2HOT",
            "kind": "output",
            "state": "READY",
            "path": "/cache/loc2/mmustermann/results",
            "allocated_bytes": 53687091200,
            "used_bytes": 12992276070,
            "used_bytes_at": "2026-08-30T08:30:00Z",
            "file_count": 44,
            "over_allocation": False,
            "source": None,
            "created_at": "2026-08-30T08:00:00Z",
            "warm_started_at": None,
            "warm_finished_at": None,
            "last_flushed_at": None,
            "last_flush_target": None,
            "released_at": None,
            "last_transfer_id": None,
        },
    ]
}

ALLOCATIONS: dict[str, Any] = {
    "user": "mmustermann",
    "total": {
        "limit_bytes": 250 * GIB,
        "allocated_bytes": 110 * GIB,
        "used_bytes": 47 * GIB,
        "free_bytes": 140 * GIB,
    },
    "storages": [
        {
            "storage_id": "LOC2HOT",
            "limit_bytes": 200 * GIB,
            "allocated_bytes": 110 * GIB,
            "used_bytes": 47 * GIB,
            "free_bytes": 90 * GIB,
        }
    ],
}

TRANSFERS: dict[str, Any] = {
    "transfers": [
        {
            "id": 123456,
            "kind": "warm",
            "user": "mmustermann",
            "fileset_id": 1,
            "peer_ref": "HOT1:/myuser/abc",
            "state": "SUCCEEDED",
            "route": "HOT1->LOC2HOT",
            "bytes_total": 37580963840,
            "bytes_done": 37580963840,
            "files_total": 12043,
            "files_done": 12043,
            "executing_daemon_id": "hot1",
            "bwlimit_bytes_per_s": 100000000,
            "attempt": 1,
            "error_code": None,
            "error_detail": None,
            "submitted_at": "2026-08-29T07:00:00Z",
            "started_at": "2026-08-29T07:02:00Z",
            "finished_at": "2026-08-29T09:14:00Z",
        }
    ],
    "next_cursor": None,
}

PREFLIGHT: dict[str, Any] = {
    "kind": "warm",
    "source": "HOT1:/myuser/mydirectory",
    "target": "LOC2HOT:mydir",
    "path": "",
    "route": "HOT1->LOC2HOT",
    "bytes_total": 20 * GIB,
    "file_count": 12043,
    "allocation_bytes": 22548578304,
    "refresh": False,
    "estimated_start_seconds": 240,
    "estimated_duration_seconds": 9000,
}

Handler = Callable[[httpx.Request], httpx.Response]


def payload_handler(payloads: dict[str, Any]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        body = payloads.get(request.url.path)
        if body is not None and request.url.path == "/api/v1/filesets":
            wanted = request.url.params.get("name")
            if wanted is not None:
                body = {"filesets": [f for f in body["filesets"] if f["name"] == wanted]}
        if body is None:
            return httpx.Response(
                404,
                json={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "no",
                        "details": {},
                        "request_id": "01J",
                    }
                },
                headers=HEADERS,
            )
        return httpx.Response(200, json=body, headers=HEADERS)

    return handler


ALL_PAYLOADS = {
    "/api/v1/whoami": WHOAMI,
    "/api/v1/locations": LOCATIONS,
    "/api/v1/storages": STORAGES,
    "/api/v1/filesets": FILESETS,
    "/api/v1/allocations": ALLOCATIONS,
    "/api/v1/transfers": TRANSFERS,
}


@pytest.fixture
def runtime_for() -> Callable[..., Runtime]:
    def build(
        handler: Handler | None = None,
        *,
        json: bool = False,
        width: int = 80,
        tty: bool = False,
        storage: str | None = None,
    ) -> Runtime:
        chosen = handler or payload_handler(ALL_PAYLOADS)

        def make_client(settings: Settings, runtime: Runtime) -> StashClient:
            return StashClient(
                settings.server,
                FakeAuthProvider(),
                transport=httpx.MockTransport(chosen),
                sleeper=lambda seconds: None,
            )

        return Runtime(
            load_settings=lambda: Settings(server=SERVER, storage=storage, timeout=5.0),
            output=OutputOptions(json=json, color=False, width=width, tty=tty),
            sleeper=lambda seconds: None,
            make_client=make_client,
        )

    return build
