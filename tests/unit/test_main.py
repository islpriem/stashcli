"""Global options, exit codes and --json shapes."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from stashcli import __version__
from stashcli.main import main
from stashcli.runtime import Runtime
from tests.conftest import HEADERS

RuntimeFor = Callable[..., Runtime]


def envelope(status: int, code: str) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "message": "the server refused",
                    "details": {"free_bytes": 1024},
                    "request_id": "01J",
                }
            },
            headers=HEADERS,
        )

    return handler


class TestGlobalOptions:
    def test_the_version_is_printed_without_a_server(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["--version"]) == 0
        assert capsys.readouterr().out.strip() == __version__

    def test_no_command_is_a_usage_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([]) == 2

    def test_an_unknown_command_is_a_usage_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["fly"]) == 2
        assert "Traceback" not in capsys.readouterr().err

    def test_without_a_server_anywhere_the_error_says_what_to_do(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        monkeypatch.delenv("STASH_SERVER", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setattr("stashcli.main.SYSTEM_CONFIG_PRESENT", False, raising=False)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        code = main(["whoami"])

        assert code == 2
        assert "STASH_SERVER" in capsys.readouterr().err


class TestWhoAmI:
    def test_the_human_output_names_the_user_and_the_server(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["whoami"], runtime=runtime_for()) == 0

        out = capsys.readouterr().out
        assert "mmustermann (uid 1000)" in out
        assert "users, hpc-admin" in out
        assert f"stashd {__version__}" in out

    def test_json_is_one_object_with_the_server_field_names(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        assert main(["whoami"], runtime=runtime_for(json=True)) == 0

        printed = capsys.readouterr().out.strip().splitlines()
        assert len(printed) == 1
        payload = json.loads(printed[0])
        assert payload == {
            "schema_version": 1,
            "uid": 1000,
            "username": "mmustermann",
            "groups": ["users", "hpc-admin"],
            "admin": False,
            "server_version": __version__,
            "api_version": "v1",
        }


class TestListings:
    def test_locations_are_listed_with_their_state(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["locations"], runtime=runtime_for()) == 0

        out = capsys.readouterr().out
        assert "LOC1" in out and "Site 1" in out and "disabled" in out

    def test_storages_show_capacity_in_iec_and_the_drain_state(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["storages"], runtime=runtime_for()) == 0

        out = capsys.readouterr().out
        assert "500.0 TiB" in out
        assert "100.0 GiB" in out
        assert "drained" in out
        assert "cache+source" in out

    def test_json_carries_raw_bytes(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        main(["storages"], runtime=runtime_for(json=True))

        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == 1
        assert payload["storages"][1]["capacity_bytes"] == 500 * 1024**4

    def test_locations_json_lists_every_location(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        main(["locations"], runtime=runtime_for(json=True))

        payload = json.loads(capsys.readouterr().out)
        assert [entry["id"] for entry in payload["locations"]] == ["LOC1", "LOC2"]
        assert payload["locations"][1]["enabled"] is False


class TestFailures:
    @pytest.mark.parametrize(
        ("status", "code", "expected"),
        [
            (401, "UNAUTHENTICATED", 3),
            (404, "NOT_FOUND", 4),
            (409, "ALLOCATION_LIMIT_EXCEEDED", 5),
            (409, "FILESET_EXISTS", 6),
            (503, "DAEMON_UNAVAILABLE", 7),
            (500, "INTERNAL", 1),
            (418, "BREWING_TEA", 1),
        ],
    )
    def test_a_server_error_sets_its_exit_code(
        self,
        runtime_for: RuntimeFor,
        capsys: pytest.CaptureFixture[str],
        status: int,
        code: str,
        expected: int,
    ) -> None:
        assert main(["whoami"], runtime=runtime_for(envelope(status, code))) == expected

        captured = capsys.readouterr()
        assert "the server refused" in captured.err
        assert "Traceback" not in captured.err
        assert captured.out == ""

    def test_a_server_that_cannot_be_reached_is_exit_7(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        assert main(["whoami"], runtime=runtime_for(refuse)) == 7
        assert "Traceback" not in capsys.readouterr().err

    def test_munge_being_unavailable_is_exit_3_without_a_traceback(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from stashcli.auth.munge import MungeAuthProvider
        from stashcli.client.stash import StashClient
        from stashcli.config.settings import Settings

        def broken(settings: Settings, runtime: Runtime) -> StashClient:
            def encoder(socket: Any) -> str:
                raise OSError("No such file or directory: /run/munge/munge.socket.2")

            return StashClient(
                settings.server,
                MungeAuthProvider(encoder=encoder),
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
            )

        runtime = runtime_for()
        runtime.make_client = broken

        assert main(["whoami"], runtime=runtime) == 3

        captured = capsys.readouterr()
        assert "MUNGE" in captured.err
        assert "munged" in captured.err
        assert "Traceback" not in captured.err

    def test_a_credential_is_never_printed(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["whoami"], runtime=runtime_for(envelope(401, "UNAUTHENTICATED")))

        captured = capsys.readouterr()
        assert "cred-1" not in captured.err + captured.out

    def test_an_interruption_is_exit_130(
        self, runtime_for: RuntimeFor, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def interrupt(request: httpx.Request) -> httpx.Response:
            raise KeyboardInterrupt

        assert main(["whoami"], runtime=runtime_for(interrupt)) == 130


def test_starting_up_does_not_import_rich_httpx_or_pydantic() -> None:
    """`stash --help` must not pay for anything a help text does not need."""
    import subprocess
    import sys

    probe = (
        "import stashcli.main, sys;"
        "print(','.join(m for m in ('rich', 'httpx', 'pydantic') if m in sys.modules))"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)

    assert result.stdout.strip() == ""


class TestCallbackWiring:
    def test_options_without_a_command_are_a_usage_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["--json"]) == 2
        assert "no command given" in capsys.readouterr().err

    def test_the_runtime_is_built_from_the_resolved_settings(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import httpx

        from stashcli.auth.fake import FakeAuthProvider
        from stashcli.client.stash import StashClient
        from stashcli.config.settings import Settings
        from tests.conftest import ALL_PAYLOADS, payload_handler

        seen: list[Settings] = []

        def fake_client(settings: Settings, runtime: Runtime) -> StashClient:
            seen.append(settings)
            return StashClient(
                settings.server,
                FakeAuthProvider(),
                transport=httpx.MockTransport(payload_handler(ALL_PAYLOADS)),
            )

        monkeypatch.setenv("STASH_SERVER", "http://from-env:8000")
        monkeypatch.setenv("STASH_STORAGE", "LOC2HOT")
        monkeypatch.setattr("stashcli.main.default_client", fake_client)

        assert main(["whoami"]) == 0
        assert seen[0].server == "http://from-env:8000"
        assert seen[0].storage == "LOC2HOT"
        assert "mmustermann" in capsys.readouterr().out

    def test_a_bug_is_not_swallowed_into_an_exit_code(self, runtime_for: RuntimeFor) -> None:
        """Only failures that carry an exit code are turned into one; a bug still raises."""
        runtime = runtime_for()

        def explode(settings: object, run: object) -> object:
            raise ZeroDivisionError("a bug")

        runtime.make_client = explode  # type: ignore[assignment]

        with pytest.raises(ZeroDivisionError):
            main(["whoami"], runtime=runtime)


def test_the_real_client_uses_munge_and_the_configured_timeout() -> None:
    from stashcli.auth.munge import MungeAuthProvider
    from stashcli.client.stash import StashClient
    from stashcli.config.settings import Settings
    from stashcli.main import default_client
    from stashcli.render.output import OutputOptions

    settings = Settings(server="http://controller:8000", storage=None, timeout=7.0)
    runtime = Runtime(settings=settings, output=OutputOptions(), make_client=default_client)

    client = default_client(settings, runtime)

    assert isinstance(client, StashClient)
    assert isinstance(client._auth, MungeAuthProvider)
    assert client._client.timeout.read == 7.0
    client.close()


def test_the_package_exposes_only_its_version() -> None:
    import stashcli

    assert stashcli.__version__
    with pytest.raises(AttributeError):
        _ = stashcli.no_such_thing
