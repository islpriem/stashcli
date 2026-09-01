"""MUNGE credentials.

A credential is single-use: it is created for one request and never reused, not even for a
retry of that request. It is never printed.
"""

from collections.abc import Callable
from pathlib import Path

from stashcli.errors import AuthUnavailable

Encoder = Callable[[Path | None], str]


def encode_with_libmunge(socket: Path | None) -> str:  # pragma: no cover - needs munged
    import pymunge

    with pymunge.MungeContext() as context:
        if socket is not None:
            context.socket = str(socket)
        credential: bytes = context.encode()
        return credential.decode("ascii")


class MungeAuthProvider:
    scheme = "Munge"

    def __init__(
        self, socket: Path | None = None, encoder: Encoder = encode_with_libmunge
    ) -> None:
        self._socket = socket
        self._encode = encoder

    def credential(self) -> str:
        try:
            return self._encode(self._socket)
        except Exception as error:
            raise AuthUnavailable(str(error)) from None
