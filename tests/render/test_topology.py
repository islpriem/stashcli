"""Human output, pinned at 80 and 120 columns."""

import io
from collections.abc import Callable

import pytest

from stashcli.models.topology import Location, Storage, WhoAmI
from stashcli.render.output import OutputOptions
from stashcli.render.topology import render_locations, render_storages, render_whoami
from tests.conftest import LOCATIONS, SERVER, STORAGES, WHOAMI

Snapshot = Callable[[str, str], None]
WIDTHS = [80, 120]


def rendered(width: int, tty: bool, draw: Callable[..., None], *args: object) -> str:
    stream = io.StringIO()
    console = OutputOptions(color=tty, width=width, tty=tty).console(stream)
    draw(console, *args)
    return stream.getvalue()


@pytest.mark.parametrize("width", WIDTHS)
def test_whoami(assert_snapshot: Snapshot, width: int) -> None:
    text = rendered(width, False, render_whoami, WhoAmI.model_validate(WHOAMI), SERVER)

    assert_snapshot(f"whoami_{width}", text)


@pytest.mark.parametrize("width", WIDTHS)
def test_locations(assert_snapshot: Snapshot, width: int) -> None:
    locations = [Location.model_validate(entry) for entry in LOCATIONS["locations"]]

    assert_snapshot(f"locations_{width}", rendered(width, False, render_locations, locations))


@pytest.mark.parametrize("width", WIDTHS)
def test_storages(assert_snapshot: Snapshot, width: int) -> None:
    storages = [Storage.model_validate(entry) for entry in STORAGES["storages"]]

    assert_snapshot(f"storages_{width}", rendered(width, False, render_storages, storages))


class TestDegradation:
    def test_nothing_is_wider_than_the_terminal(self) -> None:
        storages = [Storage.model_validate(entry) for entry in STORAGES["storages"]]

        text = rendered(80, False, render_storages, storages)

        assert all(len(line) <= 80 for line in text.splitlines())

    def test_without_a_tty_there_is_no_ansi(self) -> None:
        storages = [Storage.model_validate(entry) for entry in STORAGES["storages"]]

        for draw, argument in ((render_storages, storages),):
            assert "\x1b[" not in rendered(80, False, draw, argument)

    def test_a_disabled_storage_says_so_rather_than_ok(self) -> None:
        storage = Storage.model_validate(STORAGES["storages"][0]).model_copy(
            update={"enabled": False}
        )

        assert "disabled" in rendered(80, False, render_storages, [storage])

    def test_an_empty_listing_says_so(self) -> None:
        assert "No storages." in rendered(80, False, render_storages, [])
        assert "No locations." in rendered(80, False, render_locations, [])
