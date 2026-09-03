"""Mirrors of the server schemas, field for field (contracts/openapi.json)."""

from pydantic import BaseModel, ConfigDict


class Wire(BaseModel):
    model_config = ConfigDict(extra="ignore")


class WhoAmI(Wire):
    uid: int
    username: str
    groups: list[str]
    admin: bool
    server_version: str
    api_version: str


class Location(Wire):
    id: str
    name: str
    enabled: bool


class Locations(Wire):
    locations: list[Location]


class Storage(Wire):
    id: str
    location: str
    roles: list[str]
    tier: str
    driver: str
    fileset_prefix: str
    capacity_bytes: int | None
    fill_limit: float
    default_user_allocation_limit_bytes: int | None
    daemon: str
    drained: bool
    enabled: bool
    quota_enforced: bool


class Storages(Wire):
    storages: list[Storage]
