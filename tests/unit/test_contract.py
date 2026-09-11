"""The response models must not drift from the vendored contract."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from stashcli.models.admin import (
    AllocationReport,
    AllocationRow,
    DrainState,
    Limit,
    Offender,
    UsageGroup,
    UsageReport,
)
from stashcli.models.filesets import (
    Allocations,
    AllocationTotals,
    Fileset,
    StorageAllocation,
    Transfer,
)
from stashcli.models.topology import Location, Storage, WhoAmI

CONTRACT = Path(__file__).parents[2] / "contracts" / "openapi.json"


def properties_of(name: str) -> set[str]:
    schemas = json.loads(CONTRACT.read_text())["components"]["schemas"]
    return set(schemas[name]["properties"])


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (WhoAmI, "WhoAmI"),
        (Location, "Location"),
        (Storage, "Storage"),
        (Fileset, "Fileset"),
        (Transfer, "Transfer"),
        (Allocations, "Allocations"),
        (AllocationTotals, "AllocationTotals"),
        (StorageAllocation, "StorageAllocation"),
    ],
)
def test_a_model_mirrors_its_server_schema(model: type[BaseModel], name: str) -> None:
    assert set(model.model_fields) == properties_of(name)


def test_the_contract_is_the_one_stashd_generated() -> None:
    document = json.loads(CONTRACT.read_text())

    assert document["info"]["title"] == "stashd"
    assert "/api/v1/whoami" in document["paths"]


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (Limit, "Limit"),
        (DrainState, "DrainState"),
        (UsageGroup, "UsageGroup"),
        (UsageReport, "UsageReport"),
        (AllocationRow, "AllocationRow"),
        (Offender, "Offender"),
        (AllocationReport, "AllocationReport"),
    ],
)
def test_an_admin_model_mirrors_its_server_schema(model: type[BaseModel], name: str) -> None:
    assert set(model.model_fields) == properties_of(name)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/whoami"),
        ("get", "/api/v1/locations"),
        ("get", "/api/v1/storages"),
        ("get", "/api/v1/filesets"),
        ("post", "/api/v1/filesets"),
        ("patch", "/api/v1/filesets/{fileset_id}"),
        ("get", "/api/v1/allocations"),
        ("get", "/api/v1/transfers"),
        ("post", "/api/v1/transfers"),
        ("get", "/api/v1/transfers/{transfer_id}"),
        ("delete", "/api/v1/transfers/{transfer_id}"),
        ("get", "/api/v1/limits"),
        ("put", "/api/v1/limits/{user}"),
        ("put", "/api/v1/limits/{user}/{storage_id}"),
        ("delete", "/api/v1/limits/{user}"),
        ("delete", "/api/v1/limits/{user}/{storage_id}"),
        ("get", "/api/v1/reports/usage"),
        ("get", "/api/v1/reports/allocation"),
        ("post", "/api/v1/storages/{storage_id}/drain"),
        ("post", "/api/v1/storages/{storage_id}/undrain"),
    ],
)
def test_every_endpoint_the_client_uses_exists(method: str, path: str) -> None:
    """The client may only call what the server says it serves."""
    paths = json.loads(CONTRACT.read_text())["paths"]

    assert method in paths.get(path, {}), f"{method.upper()} {path} is not in the contract"


def test_the_submitted_transfer_kinds_are_the_ones_the_server_accepts() -> None:
    schemas = json.loads(CONTRACT.read_text())["components"]["schemas"]

    assert {"SubmitWarm", "SubmitFlush", "SubmitRelease"} <= set(schemas)
    assert "discard" in schemas["SubmitRelease"]["properties"]
    assert "keep" in schemas["SubmitFlush"]["properties"]
