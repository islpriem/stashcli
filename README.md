# stashcli

`stash`, the command-line client for **STASH** (Storage Transfer & Allocation Scheduling
Handler). STASH stages data for HPC jobs across sites: reserve a named *fileset* on fast
cache storage, fill it from a source storage before a job runs, and write the results
back when it is done. The server is [stashd](https://github.com/islpriem/stashd).

> [!WARNING]
> STASH is a proof of concept and not suitable for production use yet.

## Features

- Stage data with `warm`, write results back with `cool`, and hand a job script its
  fileset's path with `stash path`
- A preflight before every warm: whether the allocation fits, and what the transfer costs
- Progress on a terminal, `--wait` in batch jobs
- Built for scripts: `--json` output, stable exit codes, no prompts without a terminal
- Shell completion for storage and fileset names, and a man page
- MUNGE authentication, with a fresh credential per request

## Install

Requires Python 3.12 or later, libmunge with a running `munged` that holds the cluster's
key, and a reachable stashd controller.

```bash
uv tool install git+https://github.com/islpriem/stashcli.git
```

Offline nodes can install from a wheelhouse built on a machine with the same platform and
Python: `pip wheel . -w wheels`, then `pip install --no-index --find-links wheels stashcli`.

## Quickstart

```bash
export STASH_SERVER=https://stash.example.org:8443
stash whoami                                    # who the server thinks you are
stash storages                                  # what you can stage from and to
stash warm HOT1:/data/me/genome LOC2HOT:genome --wait
stash path LOC2HOT:genome                       # one line, for job scripts
stash --yes cool LOC2HOT:genome                 # release it when done
```

For results, reserve an output fileset and write it back afterwards. It holds the only
copy of its data, so `cool` refuses to release it without `--to` or `--discard`:

```bash
stash fileset create LOC2HOT:results --size 500Gi
stash --yes cool LOC2HOT:results --to HOT1:/data/me/results --wait
```

`STORAGE:/path` names a path, `STORAGE:name` a fileset; the leading slash decides.

## Documentation

- [`docs/stash.1`](docs/stash.1), or `man -l docs/stash.1`: every command, configuration
  and exit code
- [stashd docs](https://github.com/islpriem/stashd/tree/main/docs): concepts,
  configuration, operations
- [Changelog](CHANGELOG.md)

## Development

```bash
source dev/env.sh              # keeps uv's cache and temp files in the checkout
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

`contracts/openapi.json` is copied from stashd by `scripts/sync-contract.sh`; a test fails
when the client drifts from it.

## License

MIT, see [LICENSE](LICENSE).
