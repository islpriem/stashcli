"""cool and release: the two ways a fileset goes away."""

import json
from typing import Any

import httpx
import pytest

from stashcli.main import main
from tests.conftest import ALL_PAYLOADS, FILESETS, HEADERS, TRANSFERS, payload_handler

RuntimeFor = Any

RELEASED = {**TRANSFERS["transfers"][0], "id": 7, "kind": "release", "state": "SUCCEEDED"}
FLUSHING = {
    **TRANSFERS["transfers"][0],
    "id": 8,
    "kind": "flush",
    "state": "SUBMITTED",
    "route": "LOC2HOT->HOT1",
    "peer_ref": "HOT1:/myuser/out",
    "bytes_done": 0,
}


def server(answer: dict[str, Any] = RELEASED, *, state: str = "READY") -> tuple[Any, list[Any]]:
    """The read payloads, plus whatever POST /transfers should answer."""
    seen: list[dict[str, Any]] = []
    listed = [dict(row, state=state) for row in FILESETS["filesets"]]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/transfers" and request.method == "POST":
            seen.append(json.loads(request.content))
            return httpx.Response(201, json=answer, headers=HEADERS)
        if request.url.path == "/api/v1/filesets":
            wanted = request.url.params.get("name")
            rows = [row for row in listed if wanted is None or row["name"] == wanted]
            return httpx.Response(200, json={"filesets": rows}, headers=HEADERS)
        return payload_handler(ALL_PAYLOADS)(request)

    return handler, seen


class TestReleasing:
    def test_a_cached_fileset_is_released_without_ceremony(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, sent = server()

        code = main(["--yes", "cool", "LOC2HOT:abc"], runtime=runtime_for(handler))

        assert code == 0
        assert sent == [{"kind": "release", "target": {"storage": "LOC2HOT", "fileset": "abc"}}]
        assert "Released LOC2HOT:abc" in capsys.readouterr().out

    def test_discard_is_passed_to_the_server_which_owns_the_rule(
        self, runtime_for: RuntimeFor
    ) -> None:
        handler, sent = server()

        code = main(
            ["--yes", "cool", "LOC2HOT:results", "--discard"], runtime=runtime_for(handler)
        )

        assert code == 0
        assert sent[0]["discard"] is True

    def test_the_cli_does_not_decide_what_may_be_released(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An output fileset with no target: the refusal comes from the server."""
        refusal = httpx.Response(
            400,
            json={
                "error": {
                    "code": "FLUSH_TARGET_REQUIRED",
                    "message": "results holds the only copy of its data",
                    "details": {},
                    "request_id": "01J",
                }
            },
            headers=HEADERS,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/transfers" and request.method == "POST":
                return refusal
            return payload_handler(ALL_PAYLOADS)(request)

        code = main(["--yes", "cool", "LOC2HOT:results"], runtime=runtime_for(handler))

        assert code == 6
        assert "only copy" in capsys.readouterr().err

    def test_release_is_the_same_thing_said_plainly(self, runtime_for: RuntimeFor) -> None:
        handler, sent = server()

        code = main(["--yes", "release", "LOC2HOT:abc"], runtime=runtime_for(handler))

        assert code == 0
        assert sent == [{"kind": "release", "target": {"storage": "LOC2HOT", "fileset": "abc"}}]

    def test_release_force_says_the_data_is_not_wanted(self, runtime_for: RuntimeFor) -> None:
        handler, sent = server()

        code = main(
            ["--yes", "release", "LOC2HOT:results", "--force"], runtime=runtime_for(handler)
        )

        assert code == 0
        assert sent[0]["discard"] is True


class TestConfirming:
    def test_without_a_terminal_it_needs_yes(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, sent = server()

        code = main(["cool", "LOC2HOT:abc"], runtime=runtime_for(handler, tty=False))

        captured = capsys.readouterr()
        assert code == 2
        assert sent == [], "nothing was asked of the server"
        assert "--yes" in captured.err

    def test_release_needs_yes_off_a_terminal_too(self, runtime_for: RuntimeFor) -> None:
        handler, sent = server()

        code = main(["release", "LOC2HOT:abc"], runtime=runtime_for(handler, tty=False))

        assert code == 2
        assert sent == []

    def test_on_a_terminal_it_asks_and_a_no_changes_nothing(
        self,
        runtime_for: RuntimeFor,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        handler, sent = server()
        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: False)

        code = main(["cool", "LOC2HOT:abc"], runtime=runtime_for(handler, tty=True))

        assert code == 130
        assert sent == []

    def test_on_a_terminal_a_yes_goes_ahead(
        self, runtime_for: RuntimeFor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler, sent = server()
        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: True)

        code = main(["cool", "LOC2HOT:abc"], runtime=runtime_for(handler, tty=True))

        assert code == 0
        assert len(sent) == 1

    def test_keeping_the_fileset_destroys_nothing_so_it_does_not_ask(
        self, runtime_for: RuntimeFor
    ) -> None:
        handler, sent = server(FLUSHING)

        code = main(
            ["cool", "LOC2HOT:results", "--to", "HOT1:/myuser/out", "--keep"],
            runtime=runtime_for(handler, tty=False),
        )

        assert code == 0, "no --yes needed: a kept fileset loses nothing"
        assert sent[0]["keep"] is True


class TestFlushing:
    def test_a_target_makes_it_a_flush(self, runtime_for: RuntimeFor) -> None:
        handler, sent = server(FLUSHING)

        code = main(
            ["--yes", "cool", "LOC2HOT:results", "--to", "HOT1:/myuser/out"],
            runtime=runtime_for(handler),
        )

        assert code == 0
        assert sent == [
            {
                "kind": "flush",
                "source": {"storage": "LOC2HOT", "fileset": "results"},
                "target": {"storage": "HOT1", "path": "/myuser/out"},
                "keep": False,
            }
        ]

    def test_it_says_what_was_queued_and_how_to_follow_it(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = server(FLUSHING)

        main(
            ["--yes", "cool", "LOC2HOT:results", "--to", "HOT1:/myuser/out"],
            runtime=runtime_for(handler),
        )

        out = capsys.readouterr().out
        assert "HOT1:/myuser/out" in out
        assert "stash status 8 --watch" in out

    def test_a_target_that_is_a_fileset_is_a_usage_error(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, sent = server(FLUSHING)

        code = main(
            ["--yes", "cool", "LOC2HOT:results", "--to", "HOT1:notapath"],
            runtime=runtime_for(handler),
        )

        assert code == 2
        assert sent == []
        assert "path" in capsys.readouterr().err

    def test_discard_and_to_together_are_a_usage_error(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, sent = server(FLUSHING)

        code = main(
            ["--yes", "cool", "LOC2HOT:results", "--to", "HOT1:/myuser/out", "--discard"],
            runtime=runtime_for(handler),
        )

        assert code == 2
        assert sent == []

    def test_wait_follows_the_flush_to_its_end(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        done = {**FLUSHING, "state": "SUCCEEDED", "bytes_done": FLUSHING["bytes_total"]}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/transfers" and request.method == "POST":
                return httpx.Response(201, json=FLUSHING, headers=HEADERS)
            if request.url.path == "/api/v1/transfers/8":
                return httpx.Response(200, json=done, headers=HEADERS)
            return payload_handler(ALL_PAYLOADS)(request)

        code = main(
            ["--yes", "cool", "LOC2HOT:results", "--to", "HOT1:/myuser/out", "--wait"],
            runtime=runtime_for(handler),
        )

        assert code == 0
        assert "transfer 8: SUCCEEDED" in capsys.readouterr().out


class TestJsonOutput:
    def test_a_release_answers_with_the_transfer(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = server()

        code = main(
            ["--json", "--yes", "cool", "LOC2HOT:abc"], runtime=runtime_for(handler, json=True)
        )

        out = capsys.readouterr().out
        assert code == 0
        assert out.count("\n") == 1
        assert json.loads(out)["transfer"]["kind"] == "release"

    def test_a_flush_answers_with_the_transfer(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = server(FLUSHING)

        code = main(
            ["--json", "--yes", "cool", "LOC2HOT:results", "--to", "HOT1:/myuser/out"],
            runtime=runtime_for(handler, json=True),
        )

        assert code == 0
        assert json.loads(capsys.readouterr().out)["transfer"]["kind"] == "flush"
