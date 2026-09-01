"""The HTTP client. No test reaches the network."""

import json
from typing import Any

import httpx
import pytest

from stashcli import __version__
from stashcli.auth.fake import FakeAuthProvider
from stashcli.client.stash import StashClient
from stashcli.errors import CliError, ServerError, TransportError

WHOAMI = {
    "uid": 1000,
    "username": "mmustermann",
    "groups": ["users"],
    "admin": False,
    "server_version": __version__,
    "api_version": "v1",
}
HEADERS = {"X-Stash-Api-Version": "v1", "X-Stash-Server-Version": __version__}


def client(handler: Any, **kwargs: Any) -> StashClient:
    return StashClient(
        "http://controller:8000",
        FakeAuthProvider(),
        transport=httpx.MockTransport(handler),
        sleeper=lambda seconds: None,
        **kwargs,
    )


def responder(*responses: httpx.Response) -> tuple[Any, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return handler, seen


def ok(payload: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(200, json=payload or WHOAMI, headers=HEADERS)


def envelope(status: int, code: str, **details: Any) -> httpx.Response:
    return httpx.Response(
        status,
        json={
            "error": {
                "code": code,
                "message": "the server explained itself",
                "details": details,
                "request_id": "01J",
            }
        },
        headers=HEADERS,
    )


class TestCredentials:
    def test_each_request_carries_a_fresh_credential(self) -> None:
        handler, seen = responder(ok())
        api = client(handler)

        api.whoami()
        api.whoami()

        credentials = [request.headers["Authorization"] for request in seen]
        assert credentials == ["Munge cred-1", "Munge cred-2"]

    def test_a_retry_does_not_reuse_the_credential(self) -> None:
        handler, seen = responder(httpx.Response(503, headers=HEADERS), ok())
        api = client(handler)

        api.whoami()

        credentials = [request.headers["Authorization"] for request in seen]
        assert credentials == ["Munge cred-1", "Munge cred-2"]


class TestRetries:
    def test_a_get_is_retried_three_times_then_gives_up(self) -> None:
        handler, seen = responder(httpx.Response(503, headers=HEADERS))
        api = client(handler)

        with pytest.raises(TransportError):
            api.whoami()

        assert len(seen) == 3

    def test_the_backoff_grows_and_honours_retry_after(self) -> None:
        slept: list[float] = []
        handler, _ = responder(
            httpx.Response(503, headers={**HEADERS, "Retry-After": "7"}),
            httpx.Response(503, headers=HEADERS),
            ok(),
        )
        api = StashClient(
            "http://controller:8000",
            FakeAuthProvider(),
            transport=httpx.MockTransport(handler),
            sleeper=slept.append,
        )

        api.whoami()

        assert slept == [7.0, 4.0]

    def test_an_unparseable_retry_after_falls_back_to_the_schedule(self) -> None:
        slept: list[float] = []
        handler, _ = responder(
            httpx.Response(
                503, headers={**HEADERS, "Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
            ),
            ok(),
        )
        api = StashClient(
            "http://controller:8000",
            FakeAuthProvider(),
            transport=httpx.MockTransport(handler),
            sleeper=slept.append,
        )

        api.whoami()

        assert slept == [2.0]

    def test_a_connection_failure_is_retried_and_then_reported(self) -> None:
        attempts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(TransportError) as excinfo:
            client(handler).whoami()

        assert len(attempts) == 3
        assert excinfo.value.exit_code == 7

    def test_a_client_error_is_never_retried(self) -> None:
        handler, seen = responder(envelope(404, "NOT_FOUND"))

        with pytest.raises(ServerError):
            client(handler).whoami()

        assert len(seen) == 1

    def test_only_idempotent_methods_are_retried(self) -> None:
        api = client(responder(ok())[0])

        assert api.retryable("GET")
        assert not api.retryable("POST")
        assert not api.retryable("PATCH")
        assert not api.retryable("DELETE")


class TestErrors:
    def test_an_error_envelope_becomes_a_server_error(self) -> None:
        handler, _ = responder(envelope(409, "ALLOCATION_LIMIT_EXCEEDED", free_bytes=1024))

        with pytest.raises(ServerError) as excinfo:
            client(handler).whoami()

        assert excinfo.value.code == "ALLOCATION_LIMIT_EXCEEDED"
        assert excinfo.value.exit_code == 5
        assert excinfo.value.details == {"free_bytes": 1024}
        assert excinfo.value.message == "the server explained itself"

    def test_a_body_that_is_not_an_envelope_is_still_reported(self) -> None:
        handler, _ = responder(
            httpx.Response(500, text="<html>gateway</html>", headers=HEADERS)
        )

        with pytest.raises(CliError) as excinfo:
            client(handler).whoami()

        assert excinfo.value.exit_code in (1, 7)

    def test_no_credential_ever_appears_in_an_error(self) -> None:
        handler, _ = responder(envelope(401, "UNAUTHENTICATED"))

        with pytest.raises(ServerError) as excinfo:
            client(handler).whoami()

        assert "cred-1" not in str(excinfo.value)


class TestVersions:
    def test_a_differing_server_version_warns_once(self) -> None:
        warnings: list[str] = []
        handler, _ = responder(
            httpx.Response(
                200,
                json=WHOAMI,
                headers={"X-Stash-Api-Version": "v1", "X-Stash-Server-Version": "9.9.9"},
            )
        )
        api = client(handler, on_warning=warnings.append)

        api.whoami()
        api.whoami()

        assert len(warnings) == 1
        assert "9.9.9" in warnings[0]

    def test_a_differing_api_version_aborts(self) -> None:
        handler, _ = responder(
            httpx.Response(
                200,
                json=WHOAMI,
                headers={"X-Stash-Api-Version": "v2", "X-Stash-Server-Version": __version__},
            )
        )

        with pytest.raises(CliError) as excinfo:
            client(handler).whoami()

        assert "v2" in excinfo.value.message

    def test_a_server_without_the_headers_is_accepted(self) -> None:
        handler, _ = responder(httpx.Response(200, json=WHOAMI))

        assert client(handler).whoami().username == "mmustermann"


class TestEndpoints:
    def test_whoami_returns_the_typed_model(self) -> None:
        handler, seen = responder(ok())

        result = client(handler).whoami()

        assert seen[0].url.path == "/api/v1/whoami"
        assert (result.uid, result.username, result.admin) == (1000, "mmustermann", False)

    def test_locations_and_storages_are_unwrapped(self) -> None:
        payloads = {
            "/api/v1/locations": {
                "locations": [{"id": "LOC1", "name": "Site 1", "enabled": True}]
            },
            "/api/v1/storages": {
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
                    }
                ]
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=json.dumps(payloads[request.url.path]), headers=HEADERS
            )

        api = client(handler)

        assert [location.id for location in api.locations()] == ["LOC1"]
        assert [storage.id for storage in api.storages()] == ["HOT1"]
        assert api.storages()[0].roles == ["source"]
