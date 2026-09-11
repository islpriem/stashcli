"""Dynamic completion of storage and fileset names.

A shell asks for these while the user is typing: they must be fast, and they must never
raise — a completion that fails takes the shell prompt with it.
"""

from typing import Any

import httpx
import pytest

from stashcli import completion
from tests.conftest import ALL_PAYLOADS, HEADERS, payload_handler


def answering(handler: Any) -> Any:
    return httpx.MockTransport(handler)


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Point the completion helpers at a fake server instead of the network."""

    def use(handler: Any = None, *, storage: str | None = None) -> None:
        chosen = handler or payload_handler(ALL_PAYLOADS)
        from stashcli.auth.fake import FakeAuthProvider

        monkeypatch.setattr(completion, "_transport", lambda: httpx.MockTransport(chosen))
        monkeypatch.setattr(completion, "_auth", FakeAuthProvider)
        monkeypatch.setenv("STASH_SERVER", "http://controller:8000")
        if storage is not None:
            monkeypatch.setenv("STASH_STORAGE", storage)
        else:
            monkeypatch.delenv("STASH_STORAGE", raising=False)

    return use


class TestStorageNames:
    def test_it_offers_every_storage(self, served: Any) -> None:
        served()

        assert set(completion.complete_storage("")) == {"HOT1", "LOC2HOT"}

    def test_it_narrows_to_what_was_typed(self, served: Any) -> None:
        served()

        assert completion.complete_storage("LOC") == ["LOC2HOT"]

    def test_matching_ignores_case(self, served: Any) -> None:
        served()

        assert completion.complete_storage("loc") == ["LOC2HOT"]


class TestFilesetNames:
    def test_it_offers_references_a_command_would_accept(self, served: Any) -> None:
        served()

        offered = completion.complete_fileset("")

        assert "LOC2HOT:abc" in offered
        assert "LOC2HOT:results" in offered

    def test_a_typed_storage_prefix_narrows_to_that_storage(self, served: Any) -> None:
        served()

        assert all(name.startswith("LOC2HOT:") for name in completion.complete_fileset("LOC2"))

    def test_with_a_default_storage_bare_names_are_offered(self, served: Any) -> None:
        served(storage="LOC2HOT")

        offered = completion.complete_fileset("ab")

        assert offered == ["abc"]

    def test_released_filesets_are_not_offered(self, served: Any) -> None:
        """Completing to a name that no longer exists helps nobody."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/filesets":
                assert request.url.params.get("state") == "READY"
            return payload_handler(ALL_PAYLOADS)(request)

        served(handler)

        assert completion.complete_fileset("") != []


class TestWhenTheServerIsNotThere:
    def test_an_unreachable_server_offers_nothing_rather_than_failing(
        self, served: Any
    ) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        served(refuse)

        assert completion.complete_storage("") == []
        assert completion.complete_fileset("") == []

    def test_no_configured_server_offers_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STASH_SERVER", raising=False)
        monkeypatch.setattr(completion, "_config_paths", lambda: [], raising=False)

        assert completion.complete_storage("") == []

    def test_a_server_error_offers_nothing(self, served: Any) -> None:
        def broken(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"nope": True}, headers=HEADERS)

        served(broken)

        assert completion.complete_storage("") == []


class TestBeingFastEnoughForAShell:
    def test_it_does_not_retry_an_unreachable_server(
        self, served: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A shell waits for this between keystrokes: one attempt, no backoff."""
        attempts = []

        def refuse(request: httpx.Request) -> httpx.Response:
            attempts.append(request)
            raise httpx.ConnectError("no route to host")

        served(refuse)

        assert completion.complete_storage("") == []
        assert len(attempts) == 1

    def test_it_waits_only_briefly(self, served: Any) -> None:
        served()

        client = completion._client()
        with client:  # type: ignore[union-attr]
            assert client._client.timeout.connect <= completion.TIMEOUT  # type: ignore[union-attr]
