"""Human rendering of identity and topology."""

from collections.abc import Sequence

from rich.console import Console
from rich.table import Table

from stashcli.models.topology import Location, Storage, WhoAmI
from stashcli.render.output import print_block
from stashcli.sizes import format_bytes


def table(*columns: str) -> Table:
    grid = Table(box=None, pad_edge=False, show_edge=False)
    for column in columns:
        grid.add_column(column, overflow="fold")
    return grid


def render_whoami(console: Console, whoami: WhoAmI, server: str) -> None:
    console.print(f"{whoami.username} (uid {whoami.uid})")
    console.print(f"Groups   {', '.join(whoami.groups) or '—'}")
    console.print(f"Admin    {'yes' if whoami.admin else 'no'}")
    console.print(
        f"Server   {server} · stashd {whoami.server_version} · API {whoami.api_version}"
    )


def render_locations(console: Console, locations: Sequence[Location]) -> None:
    if not locations:
        console.print("No locations.")
        return
    grid = table("ID", "NAME", "STATE")
    for location in locations:
        grid.add_row(location.id, location.name, "enabled" if location.enabled else "disabled")
    print_block(console, grid)


def render_storages(console: Console, storages: Sequence[Storage]) -> None:
    if not storages:
        console.print("No storages.")
        return
    grid = table("ID", "LOCATION", "ROLES", "TIER", "DRIVER", "CAPACITY", "USER LIMIT", "STATE")
    for storage in storages:
        grid.add_row(
            storage.id,
            storage.location,
            "+".join(storage.roles),
            storage.tier,
            storage.driver,
            format_bytes(storage.capacity_bytes),
            format_bytes(storage.default_user_allocation_limit_bytes),
            state_of(storage),
        )
    print_block(console, grid)


def state_of(storage: Storage) -> str:
    if not storage.enabled:
        return "disabled"
    return "drained" if storage.drained else "ok"
