"""Layered configuration."""

from pathlib import Path

import pytest

from stashcli.config.settings import DEFAULT_TIMEOUT, default_config_paths, resolve_settings
from stashcli.errors import UsageError


def written(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


class TestServerResolution:
    def test_the_flag_wins(self, tmp_path: Path) -> None:
        user = written(tmp_path / "user.toml", 'server = "https://from-file"\n')

        settings = resolve_settings(
            server="https://from-flag",
            env={"STASH_SERVER": "https://from-env"},
            config_paths=[user],
        )

        assert settings.server == "https://from-flag"

    def test_then_the_environment(self, tmp_path: Path) -> None:
        user = written(tmp_path / "user.toml", 'server = "https://from-file"\n')

        settings = resolve_settings(
            env={"STASH_SERVER": "https://from-env"}, config_paths=[user]
        )

        assert settings.server == "https://from-env"

    def test_then_the_user_config_before_the_system_config(self, tmp_path: Path) -> None:
        user = written(tmp_path / "user.toml", 'server = "https://user"\n')
        system = written(tmp_path / "system.toml", 'server = "https://system"\n')

        settings = resolve_settings(env={}, config_paths=[user, system])

        assert settings.server == "https://user"

    def test_then_the_system_config(self, tmp_path: Path) -> None:
        system = written(tmp_path / "system.toml", 'server = "https://system"\n')

        settings = resolve_settings(env={}, config_paths=[tmp_path / "absent.toml", system])

        assert settings.server == "https://system"

    def test_no_server_anywhere_is_a_usage_error(self) -> None:
        with pytest.raises(UsageError) as excinfo:
            resolve_settings(env={}, config_paths=[])

        assert excinfo.value.exit_code == 2
        assert excinfo.value.hint is not None
        assert "STASH_SERVER" in excinfo.value.hint


class TestOtherSettings:
    def test_the_default_storage_follows_the_same_order(self, tmp_path: Path) -> None:
        user = written(tmp_path / "user.toml", 'server = "https://s"\nstorage = "FROMFILE"\n')

        assert resolve_settings(env={}, config_paths=[user]).storage == "FROMFILE"
        assert (
            resolve_settings(env={"STASH_STORAGE": "FROMENV"}, config_paths=[user]).storage
            == "FROMENV"
        )
        assert (
            resolve_settings(storage="FROMFLAG", env={}, config_paths=[user]).storage
            == "FROMFLAG"
        )

    def test_there_is_no_default_storage_unless_one_is_configured(self, tmp_path: Path) -> None:
        user = written(tmp_path / "user.toml", 'server = "https://s"\n')

        assert resolve_settings(env={}, config_paths=[user]).storage is None

    def test_the_timeout_has_a_default_and_can_be_overridden(self, tmp_path: Path) -> None:
        user = written(tmp_path / "user.toml", 'server = "https://s"\ntimeout = 5\n')

        assert resolve_settings(env={}, config_paths=[user]).timeout == 5.0
        assert resolve_settings(timeout=1.5, env={}, config_paths=[user]).timeout == 1.5
        assert (
            resolve_settings(
                env={}, config_paths=[written(tmp_path / "b.toml", 'server="x"\n')]
            ).timeout
            == DEFAULT_TIMEOUT
        )


class TestConfigFiles:
    def test_a_malformed_config_file_names_itself(self, tmp_path: Path) -> None:
        broken = written(tmp_path / "broken.toml", "server = \n")

        with pytest.raises(UsageError) as excinfo:
            resolve_settings(env={}, config_paths=[broken])

        assert "broken.toml" in excinfo.value.message

    def test_an_unreadable_key_type_is_reported(self, tmp_path: Path) -> None:
        wrong = written(tmp_path / "wrong.toml", "server = 42\n")

        with pytest.raises(UsageError):
            resolve_settings(env={}, config_paths=[wrong])

    def test_the_search_path_is_user_config_then_etc(self) -> None:
        paths = default_config_paths(
            {"XDG_CONFIG_HOME": "/xdg"}, home=Path("/home/mmustermann")
        )

        assert paths == [Path("/xdg/stash/config.toml"), Path("/etc/stash/stashcli.toml")]

    def test_the_user_config_falls_back_to_dot_config(self) -> None:
        paths = default_config_paths({}, home=Path("/home/mmustermann"))

        assert paths[0] == Path("/home/mmustermann/.config/stash/config.toml")
