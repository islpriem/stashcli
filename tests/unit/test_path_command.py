"""stash path: one line, or exit 4."""

from typing import Any

import httpx
import pytest

from stashcli.main import main
from tests.conftest import ALL_PAYLOADS, FILESETS, HEADERS, payload_handler

RuntimeFor = Any


def only(state: str, name: str = "abc") -> Any:
    """A server that answers with one fileset in the state the test cares about."""
    listed = [dict(row, state=state) for row in FILESETS["filesets"] if row["name"] == name]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/filesets":
            return httpx.Response(200, json={"filesets": listed}, headers=HEADERS)
        return payload_handler(ALL_PAYLOADS)(request)

    return handler


class TestPrintingAPath:
    def test_it_prints_the_path_and_nothing_else(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["path", "LOC2HOT:abc"], runtime=runtime_for())

        captured = capsys.readouterr()
        assert code == 0
        assert captured.out == "/cache/loc2/mmustermann/abc\n"
        assert captured.err == ""

    def test_it_is_the_servers_path_not_one_the_cli_built(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/filesets":
                listed = [
                    dict(row, path="/somewhere/else/entirely")
                    for row in FILESETS["filesets"]
                    if row["name"] == "abc"
                ]
                return httpx.Response(200, json={"filesets": listed}, headers=HEADERS)
            return payload_handler(ALL_PAYLOADS)(request)

        code = main(["path", "LOC2HOT:abc"], runtime=runtime_for(handler))

        assert code == 0
        assert capsys.readouterr().out == "/somewhere/else/entirely\n"

    def test_a_bare_name_uses_the_default_storage(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["path", "abc"], runtime=runtime_for(storage="LOC2HOT"))

        assert code == 0
        assert capsys.readouterr().out == "/cache/loc2/mmustermann/abc\n"

    def test_a_bare_name_without_a_default_lists_the_candidates(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["path", "abc"], runtime=runtime_for())

        captured = capsys.readouterr()
        assert code == 2
        assert captured.out == "", "a job script parses stdout; it stays empty on failure"
        assert "LOC2HOT" in captured.err


class TestWhenThereIsNoPathToPrint:
    def test_a_fileset_that_does_not_exist_exits_4(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["path", "LOC2HOT:nothing"], runtime=runtime_for())

        captured = capsys.readouterr()
        assert code == 4
        assert captured.out == ""
        assert "nothing" in captured.err

    @pytest.mark.parametrize("state", ["CREATING", "POPULATING", "FLUSHING", "RELEASING"])
    def test_a_fileset_that_is_not_ready_exits_4(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str], state: str
    ) -> None:
        """A job that branches on this must not be pointed at partial data."""
        code = main(["path", "LOC2HOT:abc"], runtime=runtime_for(only(state)))

        captured = capsys.readouterr()
        assert code == 4
        assert captured.out == ""
        assert state in captured.err

    def test_a_released_fileset_exits_4(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["path", "LOC2HOT:abc"], runtime=runtime_for(only("RELEASED")))

        assert code == 4
        assert capsys.readouterr().out == ""

    def test_a_failed_fileset_exits_4(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["path", "LOC2HOT:abc"], runtime=runtime_for(only("FAILED")))

        assert code == 4
        assert capsys.readouterr().out == ""


class TestJsonOutput:
    def test_json_carries_the_path_and_the_state(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        code = main(["--json", "path", "LOC2HOT:abc"], runtime=runtime_for(json=True))

        body = json.loads(capsys.readouterr().out)
        assert code == 0
        assert body["path"] == "/cache/loc2/mmustermann/abc"
        assert body["state"] == "READY"
