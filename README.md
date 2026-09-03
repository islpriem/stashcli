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
```

Global options: `--server URL`, `--storage ID`, `--json`, `--no-color`, `--timeout S`,
`-v`, `-q`, `--yes`, `--version`.

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
