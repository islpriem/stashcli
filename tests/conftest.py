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
LOCATIONS = {
    "locations": [
        {"id": "LOC1", "name": "Site 1", "enabled": True},
        {"id": "LOC2", "name": "Site 2", "enabled": False},
    ]
}
STORAGES = {
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
        },
    ]
}

Handler = Callable[[httpx.Request], httpx.Response]


def payload_handler(payloads: dict[str, Any]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        body = payloads.get(request.url.path)
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
            settings=Settings(server=SERVER, storage=storage, timeout=5.0),
            output=OutputOptions(json=json, color=False, width=width, tty=tty),
            make_client=make_client,
        )

    return build
