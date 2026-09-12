# Changelog

## 0.1.1

### Added

- MIT license, shipped in the wheel and the sdist.

### Fixed

- `--help` on a subcommand (`stash warm --help`, `stash admin limit set --help`, …) works
  with no server configured: settings are resolved when a command first needs them.
- The sdist carries only the project: its include patterns are anchored to the root and
  no longer match local caches in the checkout.

## 0.1.0

### Added

- `stash` entry point: global options, layered configuration, reference parsing, and the
  exit codes.
- MUNGE authentication with one fresh credential per request, and a clear exit 3 when
  `munged` is unavailable.
- Typed HTTP client: retries only idempotent GETs, honours `Retry-After`, maps the error
  envelope, and checks the API and server version of every response.
- `whoami`, `locations` and `storages`, with human output pinned by golden files at 80 and
  120 columns and a `--json` object carrying `schema_version`.
- `fileset list` (and the `list` shorthand) with `--storage`, `--user`, `--kind`,
  `--state` and `--long`; `fileset show`, which resolves a reference and shows the
  fileset with its transfer history; `quota`, which states where an allocation is not
  enforced by the filesystem. A bare name with no default storage lists the
  storages it could have meant instead of guessing.
- `fileset create`, `fileset resize` and `warm`. A warm asks the server for a preflight,
  shows it, and then submits; a refusal marks the check that failed with the server's own
  numbers and exits with the mapped code. `--dry-run` shows the
  preflight and submits nothing. Shrinking a fileset confirms on a terminal and needs
  `--yes` without one.
- Errors print the server's code and what to do next, and no longer repeat numbers the
  server's own message already carries.
- `status`, `queue` and `cancel`. Each transfer id is its own request, so one failure does
  not hide the rest and the exit code is the worst of them.
- `--watch` on `status` and `--wait` on `warm` follow transfers to a terminal state: a
  progress bar on a terminal, a line per poll in a job log, exit 8 on failure. Ctrl-C
  detaches without cancelling. `--timeout` bounds a `--wait` and exits 1 when it runs out.
- `stash path`: the absolute path on stdout, one line, nothing else, and exit 4 when
  there is nothing worth printing, including a fileset that is not READY yet, so a job
  script can branch on it.
- `cool` and `release`. `cool --to STORAGE:/path` writes a fileset out and releases it
  unless `--keep`; without `--to` it releases. What may be released without a flush stays
  the server's rule: the CLI passes `--discard` on and renders the refusal.
  Both confirm on a terminal and need `--yes` without one.
- `stash admin`: `limit set` / `limit unset`, `report usage` / `report allocation`, and
  `drain` / `undrain`. Admin rights are the server's
  decision; the client asks and renders what comes back.
- Shell completion, with storage ids and fileset names fetched from the server, and a man
  page shipped in the wheel as `share/man/man1/stash.1`. Completion makes one
  attempt with a short timeout and offers nothing rather than failing, so a prompt never
  hangs on an unreachable controller.
