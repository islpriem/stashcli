"""status, queue, cancel and --wait."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from stashcli.main import main
from stashcli.runtime import Runtime
from tests.conftest import ALL_PAYLOADS, HEADERS, TRANSFERS, payload_handler

RuntimeFor = Callable[..., Runtime]
GIB = 1024**3
FINISHED = TRANSFERS["transfers"][0]
RUNNING = {**FINISHED, "id": 2, "state": "RUNNING", "bytes_done": 5 * GIB, "finished_at": None}


def server(**routes: Any) -> tuple[Any, list[httpx.Request]]:
    """The read payloads, plus an answer per transfer id the test cares about."""
    seen: list[httpx.Request] = []
    reads = payload_handler(ALL_PAYLOADS)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        key = f"{request.method} {request.url.path}"
        answer = routes.get(key)
        if answer is None:
            return reads(request)
        if isinstance(answer, httpx.Response):
            return answer
        if callable(answer):
            return answer(request)
        return httpx.Response(200, json=answer, headers=HEADERS)

    return handler, seen


def refusal(status: int, code: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"code": code, "message": "no", "details": {}, "request_id": "01J"}},
        headers=HEADERS,
    )


class TestStatus:
    def test_my_transfers_are_shown(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = server()

        assert main(["status"], runtime=runtime_for(handler)) == 0

        listing = next(r for r in seen if r.url.path == "/api/v1/transfers")
        assert dict(listing.url.params) == {"user": "mmustermann"}
        assert "123456" in capsys.readouterr().out

    def test_all_shows_everyones(self, runtime_for: RuntimeFor) -> None:
        handler, seen = server()

        main(["status", "--all"], runtime=runtime_for(handler))

        listing = next(r for r in seen if r.url.path == "/api/v1/transfers")
        assert dict(listing.url.params) == {}

    def test_named_transfers_are_fetched_one_by_one(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = server(
            **{"GET /api/v1/transfers/1": FINISHED, "GET /api/v1/transfers/2": RUNNING}
        )

        assert main(["status", "1", "2"], runtime=runtime_for(handler)) == 0

        assert [r.url.path for r in seen] == ["/api/v1/transfers/1", "/api/v1/transfers/2"]

    def test_one_missing_transfer_does_not_hide_the_others(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = server(
            **{
                "GET /api/v1/transfers/1": FINISHED,
                "GET /api/v1/transfers/2": refusal(404, "NOT_FOUND"),
            }
        )

        code = main(["status", "1", "2"], runtime=runtime_for(handler))

        assert code == 4, "the worst result of the two"
        captured = capsys.readouterr()
        assert "123456" in captured.out, "the one that exists was still shown"
        assert "2" in captured.err

    def test_the_filters_reach_the_server(self, runtime_for: RuntimeFor) -> None:
        handler, seen = server()

        main(["status", "--user", "jdoe", "--state", "RUNNING"], runtime=runtime_for(handler))

        listing = next(r for r in seen if r.url.path == "/api/v1/transfers")
        assert dict(listing.url.params) == {"user": "jdoe", "state": "RUNNING"}

    def test_json_is_one_object_of_transfers(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["status"], runtime=runtime_for(json=True))

        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == 1
        assert payload["transfers"][0]["id"] == 123456


class TestQueue:
    def test_the_queue_is_everyones(self, runtime_for: RuntimeFor) -> None:
        handler, seen = server()

        assert main(["queue"], runtime=runtime_for(handler)) == 0

        listing = next(r for r in seen if r.url.path == "/api/v1/transfers")
        assert "user" not in dict(listing.url.params)

    def test_it_can_be_narrowed(self, runtime_for: RuntimeFor) -> None:
        handler, seen = server()

        main(
            ["queue", "--storage", "LOC2HOT", "--route", "HOT1->LOC2HOT", "--limit", "5"],
            runtime=runtime_for(handler),
        )

        listing = next(r for r in seen if r.url.path == "/api/v1/transfers")
        assert dict(listing.url.params) == {
            "storage": "LOC2HOT",
            "route": "HOT1->LOC2HOT",
            "limit": "5",
        }


class TestCancel:
    def test_a_transfer_is_cancelled(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cancelled = {**FINISHED, "state": "CANCELLED"}
        handler, seen = server(**{"DELETE /api/v1/transfers/123456": cancelled})

        assert main(["cancel", "123456"], runtime=runtime_for(handler)) == 0

        assert seen[0].method == "DELETE"
        assert "CANCELLED" in capsys.readouterr().out

    def test_every_id_is_its_own_request_and_the_worst_result_wins(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, seen = server(
            **{
                "DELETE /api/v1/transfers/1": {**FINISHED, "id": 1, "state": "CANCELLED"},
                "DELETE /api/v1/transfers/2": refusal(409, "CONFLICT"),
                "DELETE /api/v1/transfers/3": {**FINISHED, "id": 3, "state": "CANCELLED"},
            }
        )

        code = main(["cancel", "1", "2", "3"], runtime=runtime_for(handler))

        assert code == 6
        assert [r.url.path for r in seen] == [
            "/api/v1/transfers/1",
            "/api/v1/transfers/2",
            "/api/v1/transfers/3",
        ], "it carried on after the refusal"

    def test_a_cancel_is_never_retried(self, runtime_for: RuntimeFor) -> None:
        handler, seen = server(
            **{"DELETE /api/v1/transfers/1": httpx.Response(503, headers=HEADERS)}
        )

        assert main(["cancel", "1"], runtime=runtime_for(handler)) == 7
        assert len(seen) == 1


class TestWatching:
    def _polling(self, states: list[dict[str, Any]]) -> Any:
        """Answers about the transfer that was asked for, one state per poll."""
        answers = list(states)

        def handler(request: httpx.Request) -> httpx.Response:
            answer = answers.pop(0) if len(answers) > 1 else answers[0]
            wanted = int(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={**answer, "id": wanted}, headers=HEADERS)

        return handler

    def test_watch_follows_a_transfer_to_its_end(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler = self._polling([RUNNING, RUNNING, FINISHED])

        code = main(["status", "123456", "--watch"], runtime=runtime_for(handler))

        assert code == 0
        out = capsys.readouterr().out
        assert out.count("transfer 123456") >= 3, "a line per poll, off a terminal"
        assert "SUCCEEDED" in out

    def test_a_failed_transfer_exits_8(self, runtime_for: RuntimeFor) -> None:
        failed = {**FINISHED, "state": "FAILED", "error_code": "no_space"}

        code = main(
            ["status", "123456", "--watch"], runtime=runtime_for(self._polling([failed]))
        )

        assert code == 8

    def test_ctrl_c_detaches_without_cancelling(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            raise KeyboardInterrupt

        code = main(["status", "123456", "--watch"], runtime=runtime_for(handler))

        assert code == 130
        err = capsys.readouterr().err
        assert "stash cancel 123456" in err, "how to cancel"
        assert "--watch" in err, "and how to resume watching"
        assert not [r for r in seen if r.method == "DELETE"], "it cancelled nothing"


class TestWaiting:
    def test_warm_wait_follows_the_transfer_it_submitted(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from tests.conftest import PREFLIGHT

        polls = [{**RUNNING, "id": 123456}, {**FINISHED, "id": 123456}]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/transfers" and request.method == "POST":
                body = json.loads(request.content)
                answer = PREFLIGHT if body.get("dry_run") else {**RUNNING, "id": 123456}
                return httpx.Response(201, json=answer, headers=HEADERS)
            if request.url.path == "/api/v1/transfers/123456":
                return httpx.Response(
                    200, json=polls.pop(0) if len(polls) > 1 else polls[0], headers=HEADERS
                )
            return payload_handler(ALL_PAYLOADS)(request)

        code = main(
            ["warm", "HOT1:/myuser/mydirectory", "LOC2HOT:mydir", "--wait"],
            runtime=runtime_for(handler),
        )

        assert code == 0
        out = capsys.readouterr().out
        assert "Queued" in out
        assert "SUCCEEDED" in out

    def test_wait_gives_up_at_the_timeout_and_says_how_to_resume(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from tests.conftest import PREFLIGHT

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/transfers" and request.method == "POST":
                body = json.loads(request.content)
                answer = PREFLIGHT if body.get("dry_run") else {**RUNNING, "id": 123456}
                return httpx.Response(201, json=answer, headers=HEADERS)
            if request.url.path == "/api/v1/transfers/123456":
                return httpx.Response(200, json={**RUNNING, "id": 123456}, headers=HEADERS)
            return payload_handler(ALL_PAYLOADS)(request)

        code = main(
            [
                "warm",
                "HOT1:/myuser/mydirectory",
                "LOC2HOT:mydir",
                "--wait",
                "--timeout",
                "0",
            ],
            runtime=runtime_for(handler),
        )

        err = capsys.readouterr().err
        assert code == 1, "not staged, so a script must not carry on"
        assert "still running" in err
        assert "stash status 123456 --watch" in err

    def test_wait_with_json_still_prints_one_object_with_the_final_state(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from tests.conftest import PREFLIGHT

        polls = [{**RUNNING, "id": 123456}, {**FINISHED, "id": 123456}]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/transfers" and request.method == "POST":
                body = json.loads(request.content)
                answer = PREFLIGHT if body.get("dry_run") else {**RUNNING, "id": 123456}
                return httpx.Response(201, json=answer, headers=HEADERS)
            if request.url.path == "/api/v1/transfers/123456":
                return httpx.Response(
                    200, json=polls.pop(0) if len(polls) > 1 else polls[0], headers=HEADERS
                )
            return payload_handler(ALL_PAYLOADS)(request)

        code = main(
            ["--json", "warm", "HOT1:/myuser/mydirectory", "LOC2HOT:mydir", "--wait"],
            runtime=runtime_for(handler, json=True),
        )

        out = capsys.readouterr().out
        assert code == 0
        body = json.loads(out)
        assert out.count("\n") == 1, "exactly one object on stdout"
        assert body["preflight"]["route"] == PREFLIGHT["route"]
        assert body["transfer"]["id"] == 123456
        assert body["transfer"]["state"] == "SUCCEEDED"


class TestNothingToShow:
    def test_cancel_that_refuses_every_id_shows_no_empty_table(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = server(
            **{
                "DELETE /api/v1/transfers/99999": httpx.Response(
                    404,
                    json={
                        "error": {"code": "NOT_FOUND", "message": "no transfer with id 99999"}
                    },
                    headers=HEADERS,
                )
            }
        )

        code = main(["cancel", "99999"], runtime=runtime_for(handler))

        captured = capsys.readouterr()
        assert code == 4
        assert "transfer 99999: no transfer with id 99999" in captured.err
        assert captured.out == "", "the errors were already said; an empty table adds nothing"
