"""fileset create, fileset resize and warm."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from stashcli.main import main
from stashcli.runtime import Runtime
from tests.conftest import (
    ALL_PAYLOADS,
    FILESETS,
    HEADERS,
    PREFLIGHT,
    TRANSFERS,
    payload_handler,
)

RuntimeFor = Callable[..., Runtime]
GIB = 1024**3
CREATED = {**FILESETS["filesets"][1], "path": "/cache/loc2/mmustermann/results"}
QUEUED = {**TRANSFERS["transfers"][0], "state": "ASSIGNED"}


def routed(**overrides: Any) -> tuple[Any, list[httpx.Request]]:
    """The read payloads, plus an answer for each mutation the tests exercise."""
    seen: list[httpx.Request] = []
    reads = payload_handler(ALL_PAYLOADS)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        key = f"{request.method} {request.url.path}"
        answer = overrides.get(key)
        if answer is None and request.method in ("POST", "PATCH"):
            answer = {
                "POST /api/v1/filesets": CREATED,
                "PATCH /api/v1/filesets/2": CREATED,
            }.get(key)
            if key == "POST /api/v1/transfers":
                answer = PREFLIGHT if json.loads(request.content).get("dry_run") else QUEUED
        if answer is None:
            return reads(request)
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(201, json=answer, headers=HEADERS)

    return handler, seen


def refusal(status: int, code: str, **details: Any) -> httpx.Response:
    return httpx.Response(
        status,
        json={
            "error": {
                "code": code,
                "message": "the server refused",
                "details": details,
                "request_id": "01J",
            }
        },
        headers=HEADERS,
    )


class TestCreate:
    def test_a_fileset_is_created_and_its_path_printed(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = routed()

        code = main(
            ["fileset", "create", "LOC2HOT:results", "--size", "500Gi"],
            runtime=runtime_for(handler),
        )

        assert code == 0
        body = json.loads(next(r for r in seen if r.method == "POST").content)
        assert body == {"storage": "LOC2HOT", "name": "results", "size_bytes": 500 * GIB}
        out = capsys.readouterr().out
        assert "LOC2HOT:results" in out
        assert "/cache/loc2/mmustermann/results" in out

    def test_500G_and_500Gi_are_different_sizes(self, runtime_for: RuntimeFor) -> None:
        handler, seen = routed()

        main(["fileset", "create", "LOC2HOT:a", "--size", "500G"], runtime=runtime_for(handler))

        assert json.loads(seen[-1].content)["size_bytes"] == 500 * 1000**3

    def test_a_bad_size_is_a_usage_error_before_anything_is_sent(
        self, runtime_for: RuntimeFor
    ) -> None:
        handler, seen = routed()

        assert (
            main(
                ["fileset", "create", "LOC2HOT:a", "--size", "big"],
                runtime=runtime_for(handler),
            )
            == 2
        )
        assert not seen

    def test_a_bare_name_needs_a_storage(self, runtime_for: RuntimeFor) -> None:
        assert (
            main(["fileset", "create", "results", "--size", "1Gi"], runtime=runtime_for()) == 2
        )

    def test_a_refusal_shows_the_servers_numbers(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = routed(
            **{
                "POST /api/v1/filesets": refusal(
                    409,
                    "ALLOCATION_LIMIT_EXCEEDED",
                    required_bytes=200 * GIB,
                    free_bytes=90 * GIB,
                    limit_bytes=200 * GIB,
                    scope="storage",
                    storage="LOC2HOT",
                )
            }
        )

        code = main(
            ["fileset", "create", "LOC2HOT:results", "--size", "200Gi"],
            runtime=runtime_for(handler),
        )

        assert code == 5
        err = capsys.readouterr().err
        assert "90.0 GiB free" in err
        assert "Traceback" not in err

    def test_json_is_the_created_fileset(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = routed()

        main(
            ["fileset", "create", "LOC2HOT:results", "--size", "500Gi"],
            runtime=runtime_for(handler, json=True),
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == 1
        assert payload["fileset"]["path"] == "/cache/loc2/mmustermann/results"


class TestResize:
    def test_growing_needs_no_confirmation(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = routed()

        code = main(
            ["fileset", "resize", "LOC2HOT:results", "--size", "100Gi"],
            runtime=runtime_for(handler),
        )

        assert code == 0
        patch = next(r for r in seen if r.method == "PATCH")
        assert patch.url.path == "/api/v1/filesets/2"
        assert json.loads(patch.content) == {"size_bytes": 100 * GIB, "force": False}

    def test_shrinking_without_a_terminal_needs_yes(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = routed()

        code = main(
            ["fileset", "resize", "LOC2HOT:results", "--size", "1Gi"],
            runtime=runtime_for(handler),
        )

        assert code == 2
        assert "--yes" in capsys.readouterr().err
        assert not [r for r in seen if r.method == "PATCH"], "nothing was changed"

    def test_yes_allows_the_shrink(self, runtime_for: RuntimeFor) -> None:
        handler, seen = routed()

        code = main(
            ["--yes", "fileset", "resize", "LOC2HOT:results", "--size", "1Gi"],
            runtime=runtime_for(handler),
        )

        assert code == 0
        assert [r for r in seen if r.method == "PATCH"]

    def test_force_is_passed_to_the_server_which_decides(self, runtime_for: RuntimeFor) -> None:
        handler, seen = routed()

        main(
            ["--yes", "fileset", "resize", "LOC2HOT:results", "--size", "1Gi", "--force"],
            runtime=runtime_for(handler),
        )

        assert json.loads(next(r for r in seen if r.method == "PATCH").content)["force"] is True

    def test_json_is_the_resized_fileset(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = routed()

        main(
            ["fileset", "resize", "LOC2HOT:results", "--size", "100Gi"],
            runtime=runtime_for(handler, json=True),
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["fileset"]["reference"] == "LOC2HOT:results"

    def test_declining_the_prompt_changes_nothing(
        self, runtime_for: RuntimeFor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler, seen = routed()
        monkeypatch.setattr("typer.confirm", lambda question: False)
        runtime = runtime_for(handler, tty=True)

        code = main(["fileset", "resize", "LOC2HOT:results", "--size", "1Gi"], runtime=runtime)

        assert code == 130
        assert not [r for r in seen if r.method == "PATCH"]

    def test_accepting_the_prompt_goes_ahead(
        self, runtime_for: RuntimeFor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler, seen = routed()
        monkeypatch.setattr("typer.confirm", lambda question: True)

        code = main(
            ["fileset", "resize", "LOC2HOT:results", "--size", "1Gi"],
            runtime=runtime_for(handler, tty=True),
        )

        assert code == 0
        assert [r for r in seen if r.method == "PATCH"]

    def test_a_fileset_that_is_not_there_is_exit_4(self, runtime_for: RuntimeFor) -> None:
        handler, _ = routed(**{"GET /api/v1/filesets": {"filesets": []}})

        code = main(
            ["fileset", "resize", "LOC2HOT:absent", "--size", "1Gi"],
            runtime=runtime_for(handler),
        )

        assert code == 4


class TestWarm:
    def test_a_warm_shows_the_preflight_and_what_was_queued(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = routed()

        code = main(
            ["warm", "HOT1:/myuser/mydirectory", "LOC2HOT:mydir"], runtime=runtime_for(handler)
        )

        assert code == 0
        out = capsys.readouterr().out
        assert "Preflight" in out
        assert "20.0 GiB" in out
        assert "Queued" in out
        assert "stash status 123456" in out
        submits = [r for r in seen if r.url.path == "/api/v1/transfers"]
        assert len(submits) == 2, "a dry run for the preflight, then the submission"
        assert json.loads(submits[0].content)["dry_run"] is True
        assert json.loads(submits[1].content)["dry_run"] is False

    def test_dry_run_shows_the_preflight_and_submits_nothing(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = routed()

        code = main(
            ["warm", "HOT1:/myuser/mydirectory", "LOC2HOT:mydir", "--dry-run"],
            runtime=runtime_for(handler),
        )

        assert code == 0
        out = capsys.readouterr().out
        assert "Preflight" in out
        assert "Queued" not in out
        assert "--dry-run" in out
        submits = [r for r in seen if r.url.path == "/api/v1/transfers"]
        assert len(submits) == 1
        assert json.loads(submits[0].content)["dry_run"] is True

    def test_a_dry_run_in_json_is_the_preflight_alone(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = routed()

        main(
            ["warm", "HOT1:/myuser/mydirectory", "LOC2HOT:mydir", "--dry-run"],
            runtime=runtime_for(handler, json=True),
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["preflight"]["file_count"] == 12043
        assert "transfer" not in payload

    def test_the_options_reach_the_server(self, runtime_for: RuntimeFor) -> None:
        handler, seen = routed()

        main(
            [
                "warm",
                "HOT1:/myuser/mydirectory",
                "LOC2HOT:mydir",
                "--size",
                "30Gi",
                "--refresh",
            ],
            runtime=runtime_for(handler),
        )

        body = json.loads([r for r in seen if r.url.path == "/api/v1/transfers"][-1].content)
        assert body["size_bytes"] == 30 * GIB
        assert body["refresh"] is True

    def test_a_refused_warm_marks_the_check_and_exits_5(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        answers = [
            httpx.Response(201, json=PREFLIGHT, headers=HEADERS),
            refusal(
                409,
                "ALLOCATION_LIMIT_EXCEEDED",
                required_bytes=315 * GIB,
                free_bytes=90 * GIB,
                limit_bytes=200 * GIB,
                scope="storage",
                storage="LOC2HOT",
            ),
        ]

        def transfers(request: httpx.Request) -> httpx.Response:
            return answers.pop(0)

        reads = payload_handler(ALL_PAYLOADS)

        def routing(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/transfers":
                return transfers(request)
            return reads(request)

        code = main(
            ["warm", "HOT1:/myuser/mydirectory", "LOC2HOT:mydir"], runtime=runtime_for(routing)
        )

        assert code == 5
        captured = capsys.readouterr()
        assert "✘ allocation" in captured.out
        assert "315.0 GiB needed" in captured.out
        assert "the server refused" in captured.err

    def test_a_source_that_is_not_there_is_exit_4(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = routed(
            **{"POST /api/v1/transfers": refusal(404, "PATH_NOT_FOUND", path="/myuser/absent")}
        )

        code = main(
            ["warm", "HOT1:/myuser/absent", "LOC2HOT:mydir"], runtime=runtime_for(handler)
        )

        assert code == 4
        assert "Preflight" not in capsys.readouterr().out, "there was nothing to show"

    def test_a_source_must_be_a_path_and_a_target_a_fileset(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["warm", "HOT1:mydir", "LOC2HOT:mydir"], runtime=runtime_for()) == 2
        assert main(["warm", "HOT1:/x", "LOC2HOT:/mydir"], runtime=runtime_for()) == 2

    def test_json_carries_the_preflight_and_the_transfer(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = routed()

        main(
            ["warm", "HOT1:/myuser/mydirectory", "LOC2HOT:mydir"],
            runtime=runtime_for(handler, json=True),
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["preflight"]["bytes_total"] == 20 * GIB
        assert payload["transfer"]["id"] == 123456
