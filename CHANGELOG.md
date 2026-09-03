# Changelog

## 0.1.0 — unreleased

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
