# stashcli

The STASH command-line client. Users allocate **named filesets** on cache storage, fill
them from a source storage (`warm`), and write results back out or release them (`cool`).

```bash
stash whoami
stash storages
stash locations
stash list                        # every fileset you can see, and what you have reserved
stash fileset list --storage LOC2HOT --long
stash fileset show LOC2HOT:mydir  # the record and its transfer history
stash quota                       # limits, allocation and usage per cache
stash fileset create LOC2HOT:results --size 500Gi
stash fileset resize LOC2HOT:results --size 1Ti
stash warm HOT1:/myuser/mydirectory LOC2HOT:mydir --dry-run
stash warm HOT1:/myuser/mydirectory LOC2HOT:mydir
stash warm HOT1:/myuser/mydirectory LOC2HOT:mydir --wait --timeout 3600
stash status                      # your transfers
stash status 123456 --watch       # follow one to its end
stash queue --route HOT1->LOC2HOT # what everyone is waiting for
stash cancel 123456               # what has already arrived stays
stash path LOC2HOT:mydir          # one line: where the data is
stash cool LOC2HOT:results --to HOT1:/myuser/out   # write it out, then release it
stash cool LOC2HOT:mydir          # a cached fileset is just released
stash release LOC2HOT:results --force              # release without writing anything out
```

Administration, for those the server considers admins:

```bash
stash admin limit set jdoe LOC2HOT 500Gi
stash admin limit unset jdoe LOC2HOT
stash admin report usage --group-by route --since 2026-08-01
stash admin report allocation
stash admin drain LOC2HOT
stash admin undrain LOC2HOT
```

Global options: `--server URL`, `--storage ID`, `--json`, `--no-color`, `--timeout S`,
`-v`, `-q`, `--yes`, `--version`.

## Letting a fileset go

`stash cool` is the umbrella verb, and it is deliberately hard to lose data with:

| What you type                        | Cached fileset          | Output fileset                        |
| ------------------------------------ | ----------------------- | ------------------------------------- |
| `stash cool F`                       | Released.               | **Refused** — needs `--to` or `--discard`. |
| `stash cool F --to STORAGE:/path`    | Allowed.                | Written out, then released.           |
| `... --keep`                         | Kept after writing out. | Kept after writing out.               |
| `stash release F [--force]`          | The destructive half, said plainly.               ||

The refusal comes from the server, not from this client. Anything that deletes asks
first on a terminal and needs `--yes` without one.

## Following a transfer

`--watch` on `status` and `--wait` on `warm` poll until every transfer reaches a terminal
state: a bar on a terminal, one line per poll in a job log, nothing under `-q`. `--wait`
exits 8 if the transfer failed, and 1 if `--timeout` ran out before it finished — the
transfer keeps running either way. Ctrl-C detaches without cancelling and prints how to
cancel and how to resume watching.

`--interval` (on `status --watch`) sets the seconds between polls; `--timeout` on `warm`
is how long to wait, not to be confused with the global `--timeout`, which is the
per-request HTTP timeout.

## References

A reference is `STORAGE:/path` for a path inside a storage system and `STORAGE:name` for a
fileset on one; the leading slash is the only difference. A bare `name` works when
`--storage` is given or a default storage is configured — the client never guesses.

## Configuration

The server URL comes from `--server`, then `STASH_SERVER`, then
`~/.config/stash/config.toml`, then `/etc/stash/stashcli.toml`. The same order applies to
the default storage (`--storage`, `STASH_STORAGE`, `storage` in the config).

```toml
server = "https://stash-controller:8443"
storage = "LOC2HOT"
timeout = 30
```

## Sizes

Input accepts both suffix families and they differ: `500Gi` is 500 · 1024³, `500G` is
500 · 1000³. Human output is IEC with one decimal; `--json` always carries raw bytes.

## Exit codes

| Code | Meaning                         |
| ---- | ------------------------------- |
| 0    | Success                         |
| 1    | Generic or unexpected           |
| 2    | Usage error                     |
| 3    | Authentication failed           |
| 4    | Not found                       |
| 5    | Allocation or capacity exceeded |
| 6    | Conflict or not permitted       |
| 7    | Server or storage unavailable   |
| 8    | Transfer failed (with `--wait`) |
| 130  | Interrupted                     |

## Completion and the man page

```bash
stash --install-completion     # for the current shell
stash --show-completion        # print it instead
man -l docs/stash.1            # the man page, before it is installed
```

Storage ids and fileset names are completed from the server. Completion never blocks:
one attempt, a short timeout, and nothing offered if the server cannot be reached.

## Development

```bash
source dev/env.sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
scripts/sync-contract.sh   # refetch contracts/openapi.json from the stashd checkout
```

`contracts/openapi.json` is vendored from `stashd` and never edited here; a test fails if
the response models drift from it.

An authenticated round trip against a real controller needs MUNGE. `stashd` ships a
container for it:

```bash
cd ../stashd && docker compose --profile e2e up -d e2e
docker compose exec e2e /workspace/stashd/dev/e2e/roundtrip.sh
```
