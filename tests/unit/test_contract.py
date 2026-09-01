"""The response models must not drift from the vendored contract."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from stashcli.models.topology import Location, Storage, WhoAmI

CONTRACT = Path(__file__).parents[2] / "contracts" / "openapi.json"


def properties_of(name: str) -> set[str]:
    schemas = json.loads(CONTRACT.read_text())["components"]["schemas"]
    return set(schemas[name]["properties"])


@pytest.mark.parametrize(
    ("model", "name"), [(WhoAmI, "WhoAmI"), (Location, "Location"), (Storage, "Storage")]
)
def test_a_model_mirrors_its_server_schema(model: type[BaseModel], name: str) -> None:
    assert set(model.model_fields) == properties_of(name)


def test_the_contract_is_the_one_stashd_generated() -> None:
    document = json.loads(CONTRACT.read_text())

    assert document["info"]["title"] == "stashd"
    assert "/api/v1/whoami" in document["paths"]
