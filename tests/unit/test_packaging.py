"""What gets shipped, and that it can be installed without the internet."""

import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel with the network off: a login node has no internet either."""
    out = tmp_path_factory.mktemp("dist")
    built = subprocess.run(
        ["uv", "build", "--wheel", "--offline", "--out-dir", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if built.returncode != 0:  # pragma: no cover - depends on what the cache holds
        pytest.skip(f"cannot build a wheel offline here: {built.stderr[-300:]}")
    wheels = list(out.glob("*.whl"))
    if not wheels:  # pragma: no cover
        pytest.skip("no wheel was produced")
    return wheels[0]


class TestTheWheel:
    def test_it_carries_the_package(self, wheel: Path) -> None:
        names = zipfile.ZipFile(wheel).namelist()

        assert "stashcli/main.py" in names
        assert "stashcli/completion.py" in names

    def test_it_carries_the_man_page(self, wheel: Path) -> None:
        names = zipfile.ZipFile(wheel).namelist()

        assert any(name.endswith("share/man/man1/stash.1") for name in names), names[:20]

    def test_it_declares_the_stash_entry_point(self, wheel: Path) -> None:
        with zipfile.ZipFile(wheel) as archive:
            entry_points = next(
                archive.read(name).decode()
                for name in archive.namelist()
                if name.endswith("entry_points.txt")
            )

        assert "stash = stashcli.main:cli" in entry_points

    def test_it_carries_the_mit_license(self, wheel: Path) -> None:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata = next(
                archive.read(name).decode() for name in names if name.endswith("METADATA")
            )

        assert any(".dist-info/" in name and name.endswith("/LICENSE") for name in names)
        assert "License-Expression: MIT" in metadata


@pytest.fixture(scope="module")
def sdist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The source archive, built offline like the wheel."""
    out = tmp_path_factory.mktemp("sdist")
    built = subprocess.run(
        ["uv", "build", "--sdist", "--offline", "--out-dir", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if built.returncode != 0:  # pragma: no cover - depends on what the cache holds
        pytest.skip(f"cannot build an sdist offline here: {built.stderr[-300:]}")
    return next(out.glob("*.tar.gz"))


class TestTheSdist:
    def test_it_carries_the_project_and_nothing_else(self, sdist: Path) -> None:
        """Local caches live in the checkout; include patterns must not reach into them."""
        with tarfile.open(sdist) as archive:
            top = {name.split("/")[1] for name in archive.getnames() if "/" in name}

        assert "LICENSE" in top
        assert top <= {
            "src",
            "tests",
            "docs",
            "contracts",
            "README.md",
            "CHANGELOG.md",
            "LICENSE",
            "pyproject.toml",
            "PKG-INFO",
            ".gitignore",
        }


class TestDependencies:
    def test_every_runtime_dependency_is_pinned_to_a_floor(self) -> None:
        """A login node installs from a wheelhouse: every requirement must be resolvable."""
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

        for requirement in project["dependencies"]:
            assert ">=" in requirement, f"{requirement} has no lower bound"

    def test_it_needs_nothing_but_python_312(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

        assert project["requires-python"] == ">=3.12"

    def test_the_lock_file_is_committed_so_a_wheelhouse_can_be_built(self) -> None:
        assert (ROOT / "uv.lock").is_file()
