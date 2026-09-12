# stashcli

`stash`, the command-line client for **STASH**, a data-staging service for multi-site
HPC clusters.

With STASH you reserve a named *fileset* on fast cache storage, fill it from a source
storage before a job runs, and write the results back when it is done. The server side
is [stashd](https://github.com/islpriem/stashd); its
[concepts](https://github.com/islpriem/stashd/blob/main/docs/CONCEPTS.md) guide explains
the model.

## Install

Requires Python 3.12 or later, libmunge with a running `munged` that holds the cluster's
key, and a reachable stashd controller.

```bash
uv tool install git+ssh://git@github.com/islpriem/stashcli.git
```

For nodes without internet access, build a wheelhouse on a connected machine with the
same platform and Python, then install from it:

```bash
pip wheel . -w wheels                                  # in a checkout, online
pip install --no-index --find-links wheels stashcli    # on the node
```

## Quickstart

```bash
export STASH_SERVER=https://stash.example.org:8443
stash whoami                                    # who the server thinks you are
stash storages                                  # what you can stage from and to
stash warm HOT1:/data/me/genome LOC2HOT:genome --wait
stash path LOC2HOT:genome                       # one line, for job scripts
stash --yes cool LOC2HOT:genome                 # release it when done
```

For results, reserve an output fileset and write it back afterwards:

```bash
stash fileset create LOC2HOT:results --size 500Gi
stash --yes cool LOC2HOT:results --to HOT1:/data/me/results --wait
```

An output fileset holds the only copy of its data, so `cool` refuses to release it
without `--to`, an existing directory to write it into, or `--discard`. `--keep` keeps a
fileset after writing it out.

`STORAGE:/path` names a path, `STORAGE:name` a fileset; the leading slash decides. A bare
name uses the default storage. Sizes take `500Gi` (1024-based) or `500G` (1000-based).

## Commands

| Command | Purpose |
| ------- | ------- |
| `stash whoami` | The identity the server verified |
| `stash locations`, `stash storages` | Sites, and storages with their roles, capacity and state |
| `stash list`, `stash fileset list` | Filesets with what they reserve and use |
| `stash fileset show FILESET` | One fileset and its transfer history |
| `stash fileset create TARGET --size SIZE` | Reserve an empty output fileset |
| `stash fileset resize FILESET --size SIZE` | Change a reservation |
| `stash quota` | What you reserve against your limits |
| `stash warm SOURCE TARGET` | Fill a fileset from a source storage; `--dry-run` shows the preflight |
| `stash cool FILESET` | Write a fileset out, release it, or both |
| `stash release FILESET` | Delete a fileset and free its reservation |
| `stash path FILESET` | Print where a fileset is |
| `stash status [ID...]` | Your transfers; `--watch` follows them |
| `stash queue` | What everyone is waiting for |
| `stash cancel ID...` | Stop transfers; what arrived stays |
| `stash admin limit set`, `stash admin limit unset` | Per-user allocation limits |
| `stash admin report usage`, `stash admin report allocation` | What was moved, and who holds what |
| `stash admin drain`, `stash admin undrain` | Take a storage out of service and back |

The `admin` commands need admin rights on the server. `stash COMMAND --help` and the man
page have the details.

## Configuration

Settings resolve in this order: command-line option, environment variable,
`~/.config/stash/config.toml` (or under `$XDG_CONFIG_HOME`), `/etc/stash/stashcli.toml`.

| Setting | Option | Variable | Config key |
| ------- | ------ | -------- | ---------- |
| Controller URL | `--server` | `STASH_SERVER` | `server` |
| Default storage for bare names | `--storage` | `STASH_STORAGE` | `storage` |
| HTTP timeout in seconds, default 30 | `--timeout` | | `timeout` |

```toml
server = "https://stash.example.org:8443"
storage = "LOC2HOT"
```

`--no-color` or `NO_COLOR` turns colour off. `stash --install-completion` sets up shell
completion, including storage and fileset names.

## In batch jobs

- `--json` prints exactly one JSON object on stdout, with sizes in bytes and times in UTC.
- `stash path` prints one line, so `cd "$(stash path LOC2HOT:genome)"` works; it exits 4
  while the fileset is not ready.
- `warm --wait` exits 8 if the transfer failed; with `--timeout SECONDS` it exits 1 when
  the time runs out. The transfer keeps running either way, and Ctrl-C only stops
  watching.
- Commands that delete data ask on a terminal and need `--yes` without one.

| Exit code | Meaning |
| --------- | ------- |
| 0 | Success |
| 1 | Unexpected error, or `--wait` timed out |
| 2 | Usage error |
| 3 | Authentication failed; check `munged` |
| 4 | Not found, or not ready |
| 5 | Allocation or capacity exceeded |
| 6 | Conflict or not permitted |
| 7 | Server or storage unavailable |
| 8 | Transfer failed, with `--wait` |
| 130 | Interrupted |

## Development

```bash
source dev/env.sh              # keeps uv's cache and temp files in the checkout
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

`contracts/openapi.json` is stashd's API contract, copied by `scripts/sync-contract.sh`
from a stashd checkout next to this one and never edited by hand; a test fails when the
client drifts from it. To try the client against a real controller, use the
[sandbox](https://github.com/islpriem/stashd#try-it-in-docker).

## Documentation

- [`docs/stash.1`](docs/stash.1): the man page (`man -l docs/stash.1`), installed with
  the wheel
- [stashd docs](https://github.com/islpriem/stashd/tree/main/docs): concepts,
  configuration, operations
- [Changelog](CHANGELOG.md)
