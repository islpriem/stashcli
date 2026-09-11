"""The commands hand the shell the right completer.

Checked by what each one answers against a fake server, not by identity: Typer wraps
the callback it was given.
"""

from typing import Any

import httpx
import pytest
from typer.main import get_command

from stashcli import completion
from stashcli.auth.fake import FakeAuthProvider
from stashcli.main import app
from tests.conftest import ALL_PAYLOADS, payload_handler

STORAGES = {"HOT1", "LOC2HOT"}
FILESETS = {"LOC2HOT:abc", "LOC2HOT:results"}


@pytest.fixture(autouse=True)
def served(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        completion, "_transport", lambda: httpx.MockTransport(payload_handler(ALL_PAYLOADS))
    )
    monkeypatch.setattr(completion, "_auth", FakeAuthProvider)
    monkeypatch.setenv("STASH_SERVER", "http://controller:8000")
    monkeypatch.delenv("STASH_STORAGE", raising=False)


def parameters(*path: str) -> dict[str, Any]:
    found: Any = get_command(app)
    for name in path:
        found = found.commands[name]
    return {parameter.name: parameter for parameter in found.params}


def offered(parameter: Any) -> set[str]:
    """What the shell would show: Typer hands back completion items, not strings."""
    answered = parameter._custom_shell_complete(None, parameter, "")
    return {getattr(item, "value", item) for item in answered}


class TestWhatCompletesWhat:
    @pytest.mark.parametrize(
        ("path", "argument"),
        [
            (("path",), "fileset"),
            (("cool",), "fileset"),
            (("release",), "fileset"),
            (("fileset", "show"), "fileset"),
            (("fileset", "resize"), "fileset"),
        ],
    )
    def test_a_fileset_argument_offers_fileset_names(
        self, path: tuple[str, ...], argument: str
    ) -> None:
        assert offered(parameters(*path)[argument]) == FILESETS

    @pytest.mark.parametrize(
        ("path", "argument"),
        [(("admin", "drain"), "storage"), (("admin", "undrain"), "storage")],
    )
    def test_a_storage_argument_offers_storage_ids(
        self, path: tuple[str, ...], argument: str
    ) -> None:
        assert offered(parameters(*path)[argument]) == STORAGES

    def test_the_storage_option_offers_them_too(self) -> None:
        assert offered(parameters("list")["storage"]) == STORAGES

    def test_a_size_is_not_completed_from_the_server(self) -> None:
        """Only names come from the server; anything else would be guesswork."""
        size = parameters("fileset", "create")["size"]

        assert getattr(size, "_custom_shell_complete", None) is None


class TestInstallingIt:
    def test_the_app_offers_to_install_completion(self) -> None:
        names = {parameter.name for parameter in get_command(app).params}

        assert "install_completion" in names
        assert "show_completion" in names


class TestTheShippedScripts:
    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_a_completion_script_is_produced_for_each_shell(self, shell: str) -> None:
        from typer._completion_shared import get_completion_script

        script = get_completion_script(
            prog_name="stash", complete_var="_STASH_COMPLETE", shell=shell
        )

        assert "_STASH_COMPLETE" in script
        assert "stash" in script

    def test_the_shells_own_invocation_answers(self) -> None:
        """What a shell actually runs: the completion variable, and nothing else."""
        import os
        import pathlib
        import subprocess
        import sys

        stash = pathlib.Path(sys.executable).with_name("stash")
        if not stash.exists():  # pragma: no cover - needs an installed console script
            pytest.skip("the stash console script is not installed in this environment")
        answered = subprocess.run(
            [str(stash)],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "_STASH_COMPLETE": "complete_bash",
                "COMP_WORDS": "stash sta",
                "COMP_CWORD": "1",
            },
        )

        assert answered.returncode == 0
        assert "status" in answered.stdout
