"""The credential seam. One fresh credential per request, never cached."""

from typing import Protocol


class AuthProvider(Protocol):
    scheme: str

    def credential(self) -> str: ...
