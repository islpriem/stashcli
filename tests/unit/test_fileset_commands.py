"""fileset list, fileset show and quota."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from stashcli.main import main
from stashcli.runtime import Runtime
from tests.conftest import ALL_PAYLOADS, HEADERS, payload_handler

RuntimeFor = Callable[..., Runtime]


def seen_requests(payloads: dict[str, Any] | None = None) -> tuple[Any, list[httpx.Request]]:
    handler = payload_handler(payloads or ALL_PAYLOADS)
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return recording, seen


class TestFilesetList:
    def test_the_shorthand_and_the_subcommand_agree(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["list"], runtime=runtime_for()) == 0
        shorthand = capsys.readouterr().out

        assert main(["fileset", "list"], runtime=runtime_for()) == 0

        assert capsys.readouterr().out == shorthand

    def test_the_listing_shows_the_filesets_and_the_allocation(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["list"], runtime=runtime_for())

        out = capsys.readouterr().out
        assert "abc" in out and "results" in out
        assert "All caches" in out
        assert "110.0 GiB allocated" in out

    def test_the_filters_reach_the_server(self, runtime_for: RuntimeFor) -> None:
        handler, seen = seen_requests()

        main(
            [
                "list",
                "--storage",
                "LOC2HOT",
                "--user",
                "jdoe",
                "--kind",
                "cached",
                "--state",
                "READY",
            ],
            runtime=runtime_for(handler),
        )

        listing = next(r for r in seen if r.url.path == "/api/v1/filesets")
        assert dict(listing.url.params) == {
            "storage": "LOC2HOT",
            "user": "jdoe",
            "kind": "cached",
            "state": "READY",
        }
        allocations = next(r for r in seen if r.url.path == "/api/v1/allocations")
        assert dict(allocations.url.params) == {"user": "jdoe"}

    def test_the_storage_header_is_only_fetched_when_one_storage_is_named(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = seen_requests()
        main(["list"], runtime=runtime_for(handler))
        assert not [r for r in seen if r.url.path == "/api/v1/storages"]

        handler, seen = seen_requests()
        main(["list", "--storage", "LOC2HOT"], runtime=runtime_for(handler))

        assert [r for r in seen if r.url.path == "/api/v1/storages"]
        assert "Storage LOC2HOT (LOC2, hot, posix)" in capsys.readouterr().out

    def test_json_carries_the_filesets_and_the_allocation(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["list"], runtime=runtime_for(json=True))

        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == 1
        assert [entry["name"] for entry in payload["filesets"]] == ["abc", "results"]
        assert payload["filesets"][0]["allocated_bytes"] == 39514044170
        assert payload["allocations"]["total"]["free_bytes"] == 140 * 1024**3

    def test_an_invalid_kind_is_a_usage_error(self, runtime_for: RuntimeFor) -> None:
        assert main(["list", "--kind", "sideways"], runtime=runtime_for()) == 2


class TestFilesetShow:
    def test_a_fileset_is_shown_with_its_history(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["fileset", "show", "LOC2HOT:abc"], runtime=runtime_for()) == 0

        out = capsys.readouterr().out
        assert "LOC2HOT:abc" in out
        assert "HOT1:/myuser/abc" in out
        assert "123456" in out

    def test_it_asks_the_server_for_that_one_fileset(self, runtime_for: RuntimeFor) -> None:
        handler, seen = seen_requests()

        main(["fileset", "show", "LOC2HOT:abc"], runtime=runtime_for(handler))

        listing = next(r for r in seen if r.url.path == "/api/v1/filesets")
        assert dict(listing.url.params) == {
            "storage": "LOC2HOT",
            "name": "abc",
            "user": "mmustermann",
        }
        history = next(r for r in seen if r.url.path == "/api/v1/transfers")
        assert dict(history.url.params) == {"fileset_id": "1"}

    def test_json_carries_the_fileset_and_its_transfers(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["fileset", "show", "LOC2HOT:abc"], runtime=runtime_for(json=True))

        payload = json.loads(capsys.readouterr().out)
        assert payload["fileset"]["reference"] == "LOC2HOT:abc"
        assert payload["transfers"][0]["id"] == 123456

    def test_a_fileset_that_is_not_there_is_exit_4(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payloads = {**ALL_PAYLOADS, "/api/v1/filesets": {"filesets": []}}

        code = main(
            ["fileset", "show", "LOC2HOT:absent"],
            runtime=runtime_for(payload_handler(payloads)),
        )

        assert code == 4
        assert "LOC2HOT:absent" in capsys.readouterr().err

    def test_a_bare_name_uses_the_default_storage(self, runtime_for: RuntimeFor) -> None:
        handler, seen = seen_requests()

        code = main(["fileset", "show", "abc"], runtime=runtime_for(handler, storage="LOC2HOT"))

        assert code == 0
        listing = next(r for r in seen if r.url.path == "/api/v1/filesets")
        assert dict(listing.url.params)["storage"] == "LOC2HOT"

    def test_a_bare_name_without_a_default_lists_the_candidates(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["fileset", "show", "abc"], runtime=runtime_for())

        assert code == 2
        err = capsys.readouterr().err
        assert "LOC2HOT" in err, "the caches it could have meant"
        assert "HOT1" not in err, "HOT1 holds no filesets"

    def test_a_malformed_reference_is_not_answered_with_candidates(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """It names a storage, so the storage is not what is missing."""
        handler, seen = seen_requests()

        code = main(["fileset", "show", "loc2hot:abc"], runtime=runtime_for(handler))

        assert code == 2
        assert not [r for r in seen if r.url.path == "/api/v1/storages"]
        assert "storage id" in capsys.readouterr().err

    def test_a_path_is_not_a_fileset(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["fileset", "show", "HOT1:/myuser/abc"], runtime=runtime_for())

        assert code == 2
        assert "fileset" in capsys.readouterr().err

    def test_a_server_refusal_keeps_its_exit_code(self, runtime_for: RuntimeFor) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "not yours",
                        "details": {},
                        "request_id": "01J",
                    }
                },
                headers=HEADERS,
            )

        assert main(["fileset", "show", "LOC2HOT:abc"], runtime=runtime_for(refuse)) == 6


class TestQuota:
    def test_it_shows_the_totals_and_the_storages(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["quota"], runtime=runtime_for()) == 0

        out = capsys.readouterr().out
        assert "All caches" in out
        assert "LOC2HOT" in out
        assert "not enforced" in out, "the user must be told the quota is not enforced"

    def test_another_user_can_be_asked_about(self, runtime_for: RuntimeFor) -> None:
        handler, seen = seen_requests()

        main(["quota", "--user", "jdoe"], runtime=runtime_for(handler))

        allocations = next(r for r in seen if r.url.path == "/api/v1/allocations")
        assert dict(allocations.url.params) == {"user": "jdoe"}

    def test_one_storage_can_be_singled_out(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["quota", "--storage", "NOWHERE"], runtime=runtime_for())

        assert "LOC2HOT" not in capsys.readouterr().out

    def test_json_is_the_allocation_object(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["quota"], runtime=runtime_for(json=True))

        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == 1
        assert payload["allocations"]["storages"][0]["limit_bytes"] == 200 * 1024**3
