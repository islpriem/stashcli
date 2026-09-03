"""Fileset and quota output, pinned at 80 and 120 columns."""

import io
from collections.abc import Callable
from datetime import UTC

import pytest

from stashcli.models.filesets import Allocations, Fileset, Transfer
from stashcli.models.topology import Storage
from stashcli.render.filesets import render_list, render_quota, render_show
from stashcli.render.output import OutputOptions
from tests.conftest import ALLOCATIONS, FILESETS, STORAGES, TRANSFERS

Snapshot = Callable[[str, str], None]
WIDTHS = [80, 120]

FILESET_MODELS = [Fileset.model_validate(entry) for entry in FILESETS["filesets"]]
STORAGE_MODELS = [Storage.model_validate(entry) for entry in STORAGES["storages"]]
TRANSFER_MODELS = [Transfer.model_validate(entry) for entry in TRANSFERS["transfers"]]
ALLOCATION_MODEL = Allocations.model_validate(ALLOCATIONS)


def rendered(width: int, draw: Callable[..., None], *args: object, **kwargs: object) -> str:
    stream = io.StringIO()
    console = OutputOptions(color=False, width=width, tty=False).console(stream)
    draw(console, *args, tz=UTC, **kwargs)
    return stream.getvalue()


class TestList:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_a_listing_narrowed_to_one_storage(
        self, assert_snapshot: Snapshot, width: int
    ) -> None:
        text = rendered(
            width,
            render_list,
            FILESET_MODELS,
            ALLOCATION_MODEL,
            storage=STORAGE_MODELS[1],
            long=False,
        )

        assert_snapshot(f"fileset_list_storage_{width}", text)

    @pytest.mark.parametrize("width", WIDTHS)
    def test_a_listing_across_storages(self, assert_snapshot: Snapshot, width: int) -> None:
        text = rendered(
            width, render_list, FILESET_MODELS, ALLOCATION_MODEL, storage=None, long=False
        )

        assert_snapshot(f"fileset_list_{width}", text)

    def test_long_adds_the_source_owner_and_path(self, assert_snapshot: Snapshot) -> None:
        wide = rendered(
            160, render_list, FILESET_MODELS, ALLOCATION_MODEL, storage=None, long=True
        )

        assert "/cache/loc2/mmustermann/abc" in wide
        assert "HOT1:/myuser/abc" in wide
        assert "mmustermann" in wide
        assert_snapshot(
            "fileset_list_long_120",
            rendered(
                120, render_list, FILESET_MODELS, ALLOCATION_MODEL, storage=None, long=True
            ),
        )

    def test_nothing_overflows_the_terminal(self) -> None:
        for width in WIDTHS:
            text = rendered(
                width, render_list, FILESET_MODELS, ALLOCATION_MODEL, storage=None, long=False
            )

            assert all(len(line) <= width for line in text.splitlines())

    def test_an_empty_listing_says_so_and_shows_no_table(self) -> None:
        text = rendered(80, render_list, [], ALLOCATION_MODEL, storage=None, long=False)

        assert "No filesets." in text
        assert "NAME" not in text

    def test_the_footer_names_the_directory_the_filesets_share(self) -> None:
        text = rendered(
            80, render_list, FILESET_MODELS, ALLOCATION_MODEL, storage=None, long=False
        )

        assert "Paths under /cache/loc2/mmustermann/" in text

    def test_no_footer_when_the_filesets_live_in_different_places(self) -> None:
        elsewhere = FILESET_MODELS[0].model_copy(update={"path": "/other/place/abc"})

        text = rendered(
            80,
            render_list,
            [elsewhere, FILESET_MODELS[1]],
            ALLOCATION_MODEL,
            storage=None,
            long=False,
        )

        assert "Paths under" not in text


class TestShow:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_a_cached_fileset_with_its_history(
        self, assert_snapshot: Snapshot, width: int
    ) -> None:
        text = rendered(width, render_show, FILESET_MODELS[0], TRANSFER_MODELS)

        assert_snapshot(f"fileset_show_{width}", text)

    def test_a_flushed_and_released_fileset_shows_both(self) -> None:
        history = FILESET_MODELS[0].model_copy(
            update={
                "last_flushed_at": FILESET_MODELS[0].created_at,
                "last_flush_target": "PROJECT:/myuser/abc",
                "released_at": FILESET_MODELS[0].created_at,
            }
        )

        text = rendered(80, render_show, history, [])

        assert "Flushed" in text
        assert "PROJECT:/myuser/abc" in text
        assert "Released" in text

    def test_a_fileset_over_its_allocation_is_flagged(self) -> None:
        offender = FILESET_MODELS[0].model_copy(update={"over_allocation": True})

        assert "uses more than it reserved" in rendered(80, render_show, offender, [])

    def test_an_output_fileset_has_no_source(self) -> None:
        text = rendered(80, render_show, FILESET_MODELS[1], [])

        assert "Source" not in text
        assert "no transfers" in text.lower()


class TestQuota:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_quota(self, assert_snapshot: Snapshot, width: int) -> None:
        text = rendered(width, render_quota, ALLOCATION_MODEL, STORAGE_MODELS)

        assert_snapshot(f"quota_{width}", text)

    def test_it_says_where_an_allocation_is_not_enforced(self) -> None:
        text = rendered(80, render_quota, ALLOCATION_MODEL, STORAGE_MODELS)

        assert "not enforced" in text
        assert "LOC2HOT" in text

    def test_nothing_is_said_where_every_storage_enforces_its_quota(self) -> None:
        enforcing = [
            storage.model_copy(update={"quota_enforced": True}) for storage in STORAGE_MODELS
        ]

        text = rendered(80, render_quota, ALLOCATION_MODEL, enforcing)

        assert "not enforced" not in text
