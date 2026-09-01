"""Reference parsing. Syntax only: the server owns the meaning."""

import pytest

from stashcli.errors import UsageError
from stashcli.refs import FilesetRef, PathRef, parse_reference


class TestDisambiguation:
    def test_a_leading_slash_makes_it_a_path(self) -> None:
        assert parse_reference("HOT1:/myuser/mydirectory") == PathRef(
            "HOT1", "/myuser/mydirectory"
        )

    def test_no_leading_slash_makes_it_a_fileset(self) -> None:
        assert parse_reference("LOC2HOT:mydir") == FilesetRef("LOC2HOT", "mydir")

    def test_a_reference_renders_back_to_its_text(self) -> None:
        for text in ("HOT1:/myuser/mydirectory", "LOC2HOT:mydir"):
            assert str(parse_reference(text)) == text

    def test_the_storage_root_is_a_path(self) -> None:
        assert parse_reference("HOT1:/") == PathRef("HOT1", "/")


class TestBareNames:
    def test_a_bare_name_uses_the_default_storage(self) -> None:
        assert parse_reference("mydir", default_storage="LOC2HOT") == FilesetRef(
            "LOC2HOT", "mydir"
        )

    def test_a_bare_name_without_a_default_is_a_usage_error(self) -> None:
        with pytest.raises(UsageError) as excinfo:
            parse_reference("mydir")

        assert excinfo.value.exit_code == 2
        assert excinfo.value.hint is not None
        assert "--storage" in excinfo.value.hint

    def test_an_explicit_storage_wins_over_the_default(self) -> None:
        assert parse_reference("HOT1:mydir", default_storage="LOC2HOT") == FilesetRef(
            "HOT1", "mydir"
        )

    def test_a_bare_path_is_never_accepted(self) -> None:
        with pytest.raises(UsageError):
            parse_reference("/myuser/mydirectory", default_storage="LOC2HOT")


class TestMalformed:
    @pytest.mark.parametrize(
        "text", ["", ":", ":mydir", "HOT1:", "hot1:mydir", "1HOT:/x", "HOT1:with space"]
    )
    def test_malformed_references_are_usage_errors(self, text: str) -> None:
        with pytest.raises(UsageError) as excinfo:
            parse_reference(text)

        assert excinfo.value.exit_code == 2

    @pytest.mark.parametrize("text", ["HOT1:/../etc", "HOT1:/a/../b", "HOT1:/a//b"])
    def test_a_path_that_could_escape_is_refused_before_it_is_sent(self, text: str) -> None:
        with pytest.raises(UsageError):
            parse_reference(text)

    def test_a_fileset_name_may_not_contain_a_slash(self) -> None:
        with pytest.raises(UsageError):
            parse_reference("LOC2HOT:my/dir", default_storage=None)
