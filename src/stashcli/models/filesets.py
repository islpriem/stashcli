"""Mirrors of the fileset, transfer and allocation schemas (contracts/openapi.json)."""

from datetime import datetime

from stashcli.models.topology import Wire


class Fileset(Wire):
    id: int
    name: str
    reference: str
    owner_user: str
    storage_id: str
    kind: str
    state: str
    path: str
    allocated_bytes: int
    used_bytes: int
    used_bytes_at: datetime | None
    file_count: int | None
    over_allocation: bool
    source: str | None
    created_at: datetime
    warm_started_at: datetime | None
    warm_finished_at: datetime | None
    last_flushed_at: datetime | None
    last_flush_target: str | None
    released_at: datetime | None
    last_transfer_id: int | None


class Filesets(Wire):
    filesets: list[Fileset]


class Transfer(Wire):
    id: int
    kind: str
    user: str
    fileset_id: int
    peer_ref: str | None
    state: str
    route: str
    bytes_total: int
    bytes_done: int
    files_total: int | None
    files_done: int | None
    executing_daemon_id: str | None
    bwlimit_bytes_per_s: int | None
    attempt: int
    error_code: str | None
    error_detail: str | None
    submitted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class Transfers(Wire):
    transfers: list[Transfer]
    next_cursor: str | None


class AllocationTotals(Wire):
    limit_bytes: int
    allocated_bytes: int
    used_bytes: int
    free_bytes: int


class StorageAllocation(AllocationTotals):
    storage_id: str


class Allocations(Wire):
    user: str
    total: AllocationTotals
    storages: list[StorageAllocation]
