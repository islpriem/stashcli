"""Sizes in, sizes out.

Input accepts IEC and SI suffixes and is sent as integer bytes; human output is IEC with
one decimal. ``--json`` never passes through here.
"""

import re

from stashcli.errors import UsageError

_SIZE = re.compile(r"^(?P<value>\d+)\s*(?P<prefix>[kKMGTP])?(?P<iec>i)?B?$")
_SI = {None: 1, "k": 1000, "K": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4, "P": 1000**5}
_IEC = {None: 1, "k": 1024, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
_UNITS = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")

ABSENT = "—"


def parse_size(text: str) -> int:
    """``500Gi`` is 500 · 1024³ and ``500G`` is 500 · 1000³; both are accepted."""
    match = _SIZE.match(text.strip())
    if match is None:
        raise UsageError(
            f"{text!r} is not a size",
            hint="write whole bytes or a suffix: 500Gi (1024-based) or 500G (1000-based)",
        )
    factors = _IEC if match["iec"] else _SI
    return int(match["value"]) * factors[match["prefix"]]


def format_bytes(value: int | None) -> str:
    if value is None:
        return ABSENT
    if value < 1024:
        return f"{value} B"
    size = float(value)
    for unit in _UNITS[1:-1]:
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size / 1024:.1f} {_UNITS[-1]}"
