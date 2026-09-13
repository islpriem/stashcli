"""The man page describes what the CLI actually is."""

from pathlib import Path

import pytest
from typer.main import get_command

from stashcli.main import app

ROOT = Path(__file__).resolve().parents[2]
MAN_PAGE = ROOT / "docs" / "stash.1"


def command_names() -> list[str]:
    """Every command a user can type, sub-commands written out in full."""
    found: list[str] = []

    def walk(group: object, prefix: str) -> None:
        commands = getattr(group, "commands", {})
        for name, command in commands.items():
            full = f"{prefix} {name}".strip()
            if getattr(command, "commands", None):
                walk(command, full)
            else:
                found.append(full)

    walk(get_command(app), "")
    return sorted(found)


class TestTheManPage:
    def test_it_is_shipped(self) -> None:
        assert MAN_PAGE.is_file()

    def test_it_is_a_man_page(self) -> None:
        text = MAN_PAGE.read_text()

        assert text.startswith(".TH STASH 1")
        assert ".SH NAME" in text
        assert ".SH SYNOPSIS" in text

    @pytest.mark.parametrize("command", command_names())
    def test_every_command_is_documented(self, command: str) -> None:
        if command in {"--install-completion", "--show-completion"}:
            return

        assert f"stash {command}" in MAN_PAGE.read_text(), f"{command} is not in the man page"

    def test_every_exit_code_is_documented(self) -> None:
        text = MAN_PAGE.read_text()

        for code in (0, 1, 2, 3, 4, 5, 6, 7, 8, 130):
            assert f"\n{code}\n" in text or f"{code}\t" in text or f".B {code}" in text
