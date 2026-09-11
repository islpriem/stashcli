"""stash admin: limits, reports, drain."""

import json
from typing import Any

import httpx
import pytest

from stashcli.main import main
from tests.conftest import ALL_PAYLOADS, HEADERS, payload_handler

RuntimeFor = Any
GIB = 1024**3

USAGE_REPORT: dict[str, Any] = {
    "group_by": "user",
    "since": None,
    "until": None,
    "groups": [
        {
            "key": "mmustermann",
            "bytes_transferred": 42 * GIB,
            "transfers": 7,
            "succeeded": 6,
            "success_rate": 0.857,
            "mean_queue_wait_seconds": 95.0,
            "p95_queue_wait_seconds": 240.0,
            "mean_throughput_bytes_per_s": 125000000.0,
        },
        {
            "key": "jdoe",
            "bytes_transferred": 0,
            "transfers": 1,
            "succeeded": 0,
            "success_rate": 0.0,
            "mean_queue_wait_seconds": 0.0,
            "p95_queue_wait_seconds": 0.0,
            "mean_throughput_bytes_per_s": 0.0,
        },
    ],
}
ALLOCATION_REPORT: dict[str, Any] = {
    "rows": [
        {
            "user": "mmustermann",
            "storage_id": "LOC2HOT",
            "allocated_bytes": 100 * GIB,
            "used_bytes": 60 * GIB,
            "filesets": 3,
            "limit_bytes": 200 * GIB,
        }
    ],
    "offenders": [
        {
            "user": "jdoe",
            "storage_id": "LOC2HOT",
            "fileset": "toobig",
            "allocated_bytes": GIB,
            "used_bytes": 3 * GIB,
        }
    ],
}


def server(**routes: Any) -> tuple[Any, list[httpx.Request]]:
    """The read payloads, plus an answer for the admin route under test."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        answer = routes.get(f"{request.method} {request.url.path}")
        if answer is None:
            return payload_handler(ALL_PAYLOADS)(request)
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer, headers=HEADERS)

    return handler, seen


def body_of(request: httpx.Request) -> Any:
    return json.loads(request.content)


class TestLimits:
    def test_setting_a_per_storage_limit(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        answer = {"user": "jdoe", "storage_id": "LOC2HOT", "allocation_limit_bytes": 5 * GIB}
        handler, seen = server(**{"PUT /api/v1/limits/jdoe/LOC2HOT": answer})

        code = main(
            ["admin", "limit", "set", "jdoe", "LOC2HOT", "5Gi"], runtime=runtime_for(handler)
        )

        assert code == 0
        assert body_of(seen[-1]) == {"allocation_limit_bytes": 5 * GIB}
        out = capsys.readouterr().out
        assert "jdoe" in out and "5.0 GiB" in out

    def test_setting_the_cluster_wide_limit_names_no_storage(
        self, runtime_for: RuntimeFor
    ) -> None:
        answer = {"user": "jdoe", "storage_id": None, "allocation_limit_bytes": 9 * GIB}
        handler, seen = server(**{"PUT /api/v1/limits/jdoe": answer})

        code = main(["admin", "limit", "set", "jdoe", "9Gi"], runtime=runtime_for(handler))

        assert code == 0
        assert seen[-1].url.path == "/api/v1/limits/jdoe"

    def test_unsetting_a_limit(self, runtime_for: RuntimeFor) -> None:
        handler, seen = server(
            **{"DELETE /api/v1/limits/jdoe/LOC2HOT": httpx.Response(204, headers=HEADERS)}
        )

        code = main(
            ["admin", "limit", "unset", "jdoe", "LOC2HOT"], runtime=runtime_for(handler)
        )

        assert code == 0
        assert seen[-1].method == "DELETE"

    def test_a_user_who_is_not_an_admin_is_told_by_the_server(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        refusal = httpx.Response(
            403,
            json={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "only an admin may change a limit",
                    "details": {},
                    "request_id": "01J",
                }
            },
            headers=HEADERS,
        )
        handler, _ = server(**{"PUT /api/v1/limits/jdoe/LOC2HOT": refusal})

        code = main(
            ["admin", "limit", "set", "jdoe", "LOC2HOT", "5Gi"], runtime=runtime_for(handler)
        )

        assert code == 6
        assert "only an admin" in capsys.readouterr().err

    def test_a_size_that_is_not_a_size_is_a_usage_error(self, runtime_for: RuntimeFor) -> None:
        handler, seen = server()

        code = main(
            ["admin", "limit", "set", "jdoe", "LOC2HOT", "lots"], runtime=runtime_for(handler)
        )

        assert code == 2
        assert seen == []


class TestReports:
    def test_the_usage_report_is_a_table(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = server(**{"GET /api/v1/reports/usage": USAGE_REPORT})

        code = main(["admin", "report", "usage"], runtime=runtime_for(handler))

        out = capsys.readouterr().out
        assert code == 0
        assert "mmustermann" in out
        assert "42.0 GiB" in out
        assert "86%" in out, "the success rate, as a person reads it"

    def test_the_window_and_grouping_are_passed_through(self, runtime_for: RuntimeFor) -> None:
        handler, seen = server(**{"GET /api/v1/reports/usage": USAGE_REPORT})

        code = main(
            [
                "admin",
                "report",
                "usage",
                "--group-by",
                "route",
                "--since",
                "2026-08-01",
                "--until",
                "2026-09-01",
            ],
            runtime=runtime_for(handler),
        )

        assert code == 0
        params = seen[-1].url.params
        assert params["group_by"] == "route"
        assert params["since"].startswith("2026-08-01")
        assert params["until"].startswith("2026-09-01")

    def test_an_unknown_grouping_is_refused_before_the_request(
        self, runtime_for: RuntimeFor
    ) -> None:
        handler, seen = server(**{"GET /api/v1/reports/usage": USAGE_REPORT})

        code = main(
            ["admin", "report", "usage", "--group-by", "colour"], runtime=runtime_for(handler)
        )

        assert code == 2
        assert seen == []

    def test_the_allocation_report_names_the_offenders(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = server(**{"GET /api/v1/reports/allocation": ALLOCATION_REPORT})

        code = main(["admin", "report", "allocation"], runtime=runtime_for(handler))

        out = capsys.readouterr().out
        assert code == 0
        assert "mmustermann" in out
        assert "toobig" in out
        assert "3.0 GiB" in out

    def test_a_report_can_be_json(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler, _ = server(**{"GET /api/v1/reports/usage": USAGE_REPORT})

        code = main(
            ["--json", "admin", "report", "usage"], runtime=runtime_for(handler, json=True)
        )

        out = capsys.readouterr().out
        assert code == 0
        assert out.count("\n") == 1
        assert json.loads(out)["groups"][0]["key"] == "mmustermann"


class TestDrain:
    def test_draining_a_storage(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        answer = {"storage": "LOC2HOT", "drained": True}
        handler, seen = server(**{"POST /api/v1/storages/LOC2HOT/drain": answer})

        code = main(["admin", "drain", "LOC2HOT"], runtime=runtime_for(handler))

        assert code == 0
        assert seen[-1].url.path == "/api/v1/storages/LOC2HOT/drain"
        assert "drained" in capsys.readouterr().out.lower()

    def test_undraining_a_storage(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        answer = {"storage": "LOC2HOT", "drained": False}
        handler, seen = server(**{"POST /api/v1/storages/LOC2HOT/undrain": answer})

        code = main(["admin", "undrain", "LOC2HOT"], runtime=runtime_for(handler))

        assert code == 0
        assert seen[-1].url.path == "/api/v1/storages/LOC2HOT/undrain"

    def test_an_unknown_storage_is_the_servers_answer(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        refusal = httpx.Response(
            404,
            json={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "no storage named NOPE",
                    "details": {},
                    "request_id": "01J",
                }
            },
            headers=HEADERS,
        )
        handler, _ = server(**{"POST /api/v1/storages/NOPE/drain": refusal})

        code = main(["admin", "drain", "NOPE"], runtime=runtime_for(handler))

        assert code == 4
        assert "no storage named NOPE" in capsys.readouterr().err
