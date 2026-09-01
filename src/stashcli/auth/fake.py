"""A credential provider for tests and for a server that runs without MUNGE."""

from itertools import count


class FakeAuthProvider:
    scheme = "Munge"

    def __init__(self, prefix: str = "cred") -> None:
        self._prefix = prefix
        self._numbers = count(1)

    def credential(self) -> str:
        return f"{self._prefix}-{next(self._numbers)}"
